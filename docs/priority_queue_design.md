# 优先级队列系统设计

## 当前状态分析

### Worker并行能力
- **当前实现**: 单线程顺序处理（`workers/run_worker.py` 中的 `process_loop()` 使用 `while True` 循环）
- **并行度**: 1（一次只处理一个job）
- **队列机制**: MongoDB实现的简单队列，通过 `locked_at` 字段防止并发

### 当前队列结构
```python
class QueueMessage:
    job_id: int
    payload: dict[str, Any]
    locked_at: Optional[datetime]
    completed_at: Optional[datetime]
    failed_at: Optional[datetime]
    attempts: int
    failure_reason: Optional[str]
```

### 当前API Key验证
- `validate_api_key()`: 检查API key是否存在于 `api_keys` collection
- `create_submission()`: 需要有效的API key才能创建submission和job

## 需求

1. **前端无需API Key**: 前端提交job时可以使用dummy API key "public"
2. **优先级机制**: "public" API key的job优先级最低，需要让行给其他API key的job
3. **保持向后兼容**: 现有的API key验证机制需要继续工作

## 设计方案

### 1. API Key优先级系统

#### 1.1 API Key优先级定义
```python
# 优先级值：数字越小优先级越高
PRIORITY_HIGH = 0      # 付费用户、VIP用户
PRIORITY_NORMAL = 50   # 普通注册用户
PRIORITY_LOW = 100     # "public" API key（未注册用户）
```

#### 1.2 API Keys Collection扩展
在 `api_keys` collection中添加 `priority` 字段：
```python
{
    "apikey": "user-123",
    "priority": 50,  # 默认普通优先级
    "created_at": datetime,
    ...
}

{
    "apikey": "public",
    "priority": 100,  # 最低优先级
    "is_system": true,  # 标记为系统API key
    ...
}
```

#### 1.3 特殊处理"public" API Key
- **自动创建**: 系统启动时自动创建"public" API key（如果不存在）
- **无需验证**: `validate_api_key("public")` 总是返回 `True`
- **优先级最低**: 优先级固定为 `PRIORITY_LOW` (100)

### 2. 队列消息扩展

#### 2.1 QueueMessage模型扩展
```python
class QueueMessage(MongoModel):
    job_id: int
    payload: dict[str, Any]
    priority: int = 50  # 新增：优先级字段，默认50
    api_key: str  # 新增：关联的API key，用于优先级判断
    locked_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    attempts: int = 0
    failure_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)  # 新增：用于同优先级FIFO
```

#### 2.2 优先级计算逻辑
```python
def get_api_key_priority(db, api_key: str) -> int:
    """获取API key的优先级"""
    if api_key == "public":
        return PRIORITY_LOW
    
    doc = await db["api_keys"].find_one({"apikey": api_key})
    if doc:
        return doc.get("priority", PRIORITY_NORMAL)
    
    # 如果API key不存在但验证通过（特殊情况），返回默认优先级
    return PRIORITY_NORMAL
```

### 3. 队列服务修改

#### 3.1 enqueue_job修改
```python
async def enqueue_job(
    db: AsyncIOMotorDatabase, 
    job_id: int, 
    payload: dict[str, Any],
    api_key: str  # 新增参数
) -> QueueMessage:
    """入队时记录API key和优先级"""
    priority = await get_api_key_priority(db, api_key)
    
    doc = QueueMessage(
        job_id=job_id,
        payload=payload,
        priority=priority,
        api_key=api_key,
        created_at=datetime.utcnow()
    ).model_dump(by_alias=True, exclude_none=True)
    
    result = await _collection(db).insert_one(doc)
    doc["_id"] = result.inserted_id
    return QueueMessage(**doc)
```

#### 3.2 lease_job修改（优先级排序）
```python
async def lease_job(db: AsyncIOMotorDatabase) -> Optional[QueueMessage]:
    """按优先级获取job，同优先级按创建时间FIFO"""
    now = datetime.utcnow()
    expiry = now - timedelta(seconds=settings.queue_visibility_timeout_seconds)
    
    doc = await _collection(db).find_one_and_update(
        {
            "completed_at": None,
            "failed_at": None,
            "$or": [
                {"locked_at": None},
                {"locked_at": {"$lt": expiry}},
            ],
        },
        {
            "$set": {"locked_at": now},
            "$inc": {"attempts": 1},
        },
        return_document=True,
        sort=[
            ("priority", 1),      # 优先级升序（数字小的先处理）
            ("created_at", 1),    # 同优先级按创建时间FIFO
        ],
    )
    
    if doc:
        return QueueMessage(**doc)
    return None
```

### 4. API路由修改

#### 4.1 前端路由（无需API Key）
```python
# api/routes/frontend.py
@router.post("/upload")
async def frontend_upload(
    file: UploadFile,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """前端上传，自动使用public API key"""
    api_key = "public"
    # ... 处理上传逻辑
    return await submission_service.create_submission(
        db, api_key, filename, data, upload_args
    )
```

#### 4.2 Legacy路由（保持API Key验证）
```python
# api/routes/legacy.py
@router.post("/upload")
async def upload(request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Legacy API，需要API key"""
    payload, files = await _parse_request_payload(request)
    apikey = payload.get("apikey") or payload.get("session")
    
    if not apikey:
        return _legacy_error("need session")
    
    # "public" API key也需要验证通过（特殊处理）
    if apikey != "public" and not await submission_service.validate_api_key(db, apikey):
        return _legacy_error("Invalid API key")
    
    # ... 处理上传
```

#### 4.3 validate_api_key修改
```python
async def validate_api_key(db: AsyncIOMotorDatabase, api_key: str) -> bool:
    """验证API key，public总是有效"""
    if api_key == "public":
        return True
    
    doc = await db[API_KEYS_COLLECTION].find_one({"apikey": api_key})
    return doc is not None
```

### 5. 数据库迁移

#### 5.1 创建"public" API Key
```python
async def ensure_public_api_key(db: AsyncIOMotorDatabase):
    """确保public API key存在"""
    existing = await db[API_KEYS_COLLECTION].find_one({"apikey": "public"})
    if not existing:
        await db[API_KEYS_COLLECTION].insert_one({
            "apikey": "public",
            "priority": PRIORITY_LOW,
            "is_system": True,
            "created_at": datetime.utcnow(),
            "description": "Public API key for unauthenticated users"
        })
```

#### 5.2 为现有队列消息添加优先级
```python
async def migrate_queue_priorities(db: AsyncIOMotorDatabase):
    """为现有队列消息添加优先级字段"""
    # 从submission中获取api_key，然后设置优先级
    # 如果没有关联的submission，使用默认优先级
    await db[QUEUE_COLLECTION].update_many(
        {"priority": {"$exists": False}},
        {"$set": {"priority": PRIORITY_NORMAL}}
    )
```

### 6. Worker并行化（可选，未来扩展）

#### 6.1 当前限制
- Worker是单线程的，一次只处理一个job
- `solve-field` 是CPU密集型任务，可能需要并行处理

#### 6.2 并行化方案（未来）
```python
# 使用asyncio.Semaphore限制并发数
MAX_CONCURRENT_JOBS = 2  # 可配置

async def process_loop():
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    
    async def process_single_job(msg):
        async with semaphore:
            # 处理单个job
            ...
    
    while True:
        msg = await queue_service.lease_job(db)
        if msg:
            asyncio.create_task(process_single_job(msg))
        else:
            await asyncio.sleep(2)
```

### 7. 实现步骤

1. **Phase 1: API Key优先级系统**
   - 扩展 `api_keys` collection schema
   - 创建 `ensure_public_api_key()` 函数
   - 修改 `validate_api_key()` 支持"public"
   - 添加 `get_api_key_priority()` 函数

2. **Phase 2: 队列消息扩展**
   - 扩展 `QueueMessage` 模型（添加 `priority`, `api_key`, `created_at`）
   - 修改 `enqueue_job()` 记录优先级和API key
   - 修改 `lease_job()` 按优先级排序

3. **Phase 3: API路由修改**
   - 创建前端专用上传接口（自动使用"public" API key）
   - 修改legacy接口支持"public" API key
   - 更新 `create_submission()` 传递API key到队列

4. **Phase 4: 数据库迁移**
   - 创建迁移脚本
   - 为现有数据添加优先级字段

5. **Phase 5: 测试**
   - 测试优先级排序
   - 测试"public" API key的特殊处理
   - 测试向后兼容性

## 索引优化

为了支持高效的优先级队列查询，需要在MongoDB上创建复合索引：

```javascript
db.queue_messages.createIndex(
    {
        "priority": 1,
        "created_at": 1,
        "completed_at": 1,
        "failed_at": 1,
        "locked_at": 1
    },
    {
        name: "priority_queue_index",
        partialFilterExpression: {
            completed_at: null,
            failed_at: null
        }
    }
)
```

## 监控和日志

- 记录不同优先级job的处理时间
- 监控"public" API key的job等待时间
- 记录优先级队列的统计信息

## 注意事项

1. **优先级反转**: 如果高优先级job一直入队，低优先级job可能永远无法处理。考虑：
   - 设置最大等待时间，超时后提升优先级
   - 限制高优先级job的速率

2. **公平性**: 确保"public" API key的job最终能够被处理

3. **性能**: 优先级排序查询需要合适的索引支持

