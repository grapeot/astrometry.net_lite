# Public API Key 实现方案分析

## 方案对比

### 方案1: Hard Code（代码中硬编码）

**优点：**
- ✅ **简单直接**：不需要数据库操作，性能最好
- ✅ **可靠性高**：不会因为数据库问题而失败
- ✅ **启动快**：无需等待数据库初始化
- ✅ **代码清晰**：逻辑简单，易于理解

**缺点：**
- ❌ **灵活性差**：无法动态修改优先级、禁用等
- ❌ **不一致性**：和其他API key的处理方式不同
- ❌ **扩展性差**：未来添加其他系统API key需要改代码

**实现示例：**
```python
# services/submissions.py
PUBLIC_API_KEY = "public"
PUBLIC_API_KEY_PRIORITY = 100

async def validate_api_key(db: AsyncIOMotorDatabase, api_key: str) -> bool:
    if api_key == PUBLIC_API_KEY:
        return True
    doc = await db[API_KEYS_COLLECTION].find_one({"apikey": api_key})
    return doc is not None

async def get_api_key_priority(db: AsyncIOMotorDatabase, api_key: str) -> int:
    if api_key == PUBLIC_API_KEY:
        return PUBLIC_API_KEY_PRIORITY
    doc = await db[API_KEYS_COLLECTION].find_one({"apikey": api_key})
    return doc.get("priority", 50) if doc else 50
```

### 方案2: 数据库实现（推荐）

**优点：**
- ✅ **一致性**：和其他API key一样存储在数据库中
- ✅ **灵活性**：可以通过管理接口修改优先级、禁用等
- ✅ **可扩展**：未来可以添加更多系统API key（如"demo", "guest"等）
- ✅ **可审计**：可以记录创建时间、修改历史等
- ✅ **可配置**：可以通过环境变量或配置控制行为

**缺点：**
- ⚠️ **需要初始化**：需要在应用启动时确保存在
- ⚠️ **性能略低**：需要查询数据库（但可以缓存）

**实现示例：**
```python
# services/submissions.py
PUBLIC_API_KEY = "public"
PUBLIC_API_KEY_PRIORITY = 100

async def ensure_public_api_key(db: AsyncIOMotorDatabase) -> None:
    """确保public API key存在，如果不存在则创建"""
    existing = await db[API_KEYS_COLLECTION].find_one({"apikey": PUBLIC_API_KEY})
    if not existing:
        await db[API_KEYS_COLLECTION].insert_one({
            "apikey": PUBLIC_API_KEY,
            "priority": PUBLIC_API_KEY_PRIORITY,
            "is_system": True,
            "created_at": datetime.utcnow(),
            "description": "Public API key for unauthenticated users",
            "enabled": True
        })
        logger.info("Created public API key")

async def validate_api_key(db: AsyncIOMotorDatabase, api_key: str) -> bool:
    if api_key == PUBLIC_API_KEY:
        # 即使数据库中没有，也返回True（向后兼容）
        return True
    doc = await db[API_KEYS_COLLECTION].find_one({"apikey": api_key, "enabled": True})
    return doc is not None

async def get_api_key_priority(db: AsyncIOMotorDatabase, api_key: str) -> int:
    if api_key == PUBLIC_API_KEY:
        # 优先从数据库读取，如果不存在则使用默认值
        doc = await db[API_KEYS_COLLECTION].find_one({"apikey": PUBLIC_API_KEY})
        if doc:
            return doc.get("priority", PUBLIC_API_KEY_PRIORITY)
        return PUBLIC_API_KEY_PRIORITY
    doc = await db[API_KEYS_COLLECTION].find_one({"apikey": api_key})
    return doc.get("priority", 50) if doc else 50
```

## 推荐方案：数据库实现 + 代码常量

**混合方案**：使用数据库存储，但代码中定义常量作为fallback

**理由：**
1. **一致性**：所有API key都存储在数据库中
2. **可靠性**：即使数据库中没有记录，代码常量也能保证功能正常
3. **灵活性**：可以通过数据库修改优先级
4. **向后兼容**：如果数据库初始化失败，仍然可以工作

## 注入位置分析

### 选项1: 应用启动时（lifespan）- **推荐**

**位置：** `services/mongo.py` 的 `lifespan()` 函数

**优点：**
- ✅ 应用启动时自动执行，确保public API key总是存在
- ✅ 只执行一次，性能影响小
- ✅ 如果失败，应用启动会失败，便于发现问题
- ✅ Backend和Worker都会执行（如果都使用lifespan）

**实现：**
```python
# services/mongo.py
async def lifespan(app):
    client = create_mongo_client()
    app.state.mongo_client = client
    app.state.mongo_db = get_database(client)
    
    # 初始化public API key
    from services.submissions import ensure_public_api_key
    try:
        await ensure_public_api_key(app.state.mongo_db)
    except Exception as e:
        logger.error("Failed to initialize public API key: %s", e)
        # 可以选择让应用启动失败，或者只记录警告
    
    try:
        yield
    finally:
        client.close()
```

### 选项2: Worker启动时

**位置：** `workers/run_worker.py` 的 `process_loop()` 函数

**优点：**
- ✅ Worker启动时执行
- ✅ 可以确保Worker使用的数据库有public API key

**缺点：**
- ❌ Backend也需要单独处理
- ❌ 如果Backend和Worker使用不同的数据库，需要分别初始化

**实现：**
```python
# workers/run_worker.py
async def process_loop():
    client = create_mongo_client()
    db = get_database(client)
    
    # 初始化public API key
    from services.submissions import ensure_public_api_key
    await ensure_public_api_key(db)
    
    try:
        # ... 现有逻辑
```

### 选项3: 懒加载（第一次使用时）

**位置：** `validate_api_key()` 或 `get_api_key_priority()` 函数中

**优点：**
- ✅ 不需要在启动时执行
- ✅ 按需创建

**缺点：**
- ❌ 第一次调用可能有延迟
- ❌ 如果多个地方同时调用可能产生竞态条件
- ❌ 错误处理复杂

**实现：**
```python
async def validate_api_key(db: AsyncIOMotorDatabase, api_key: str) -> bool:
    if api_key == PUBLIC_API_KEY:
        # 懒加载：如果不存在则创建
        await ensure_public_api_key(db)
        return True
    # ...
```

### 选项4: 独立初始化脚本

**位置：** 类似 `scripts/seed_api_key.py` 的独立脚本

**优点：**
- ✅ 可以手动控制何时初始化
- ✅ 可以用于数据库迁移

**缺点：**
- ❌ 需要手动执行，容易忘记
- ❌ 不适合自动化部署

## 最终推荐方案

### 推荐：数据库实现 + 应用启动时注入（lifespan）

**实现步骤：**

1. **在 `services/submissions.py` 中添加初始化函数**
```python
PUBLIC_API_KEY = "public"
PUBLIC_API_KEY_PRIORITY = 100

async def ensure_public_api_key(db: AsyncIOMotorDatabase) -> None:
    """确保public API key存在"""
    existing = await db[API_KEYS_COLLECTION].find_one({"apikey": PUBLIC_API_KEY})
    if not existing:
        await db[API_KEYS_COLLECTION].insert_one({
            "apikey": PUBLIC_API_KEY,
            "priority": PUBLIC_API_KEY_PRIORITY,
            "is_system": True,
            "created_at": datetime.utcnow(),
            "description": "Public API key for unauthenticated users",
            "enabled": True
        })
        logger.info("Created public API key")
    else:
        # 确保优先级正确（如果被修改了可以修复）
        await db[API_KEYS_COLLECTION].update_one(
            {"apikey": PUBLIC_API_KEY},
            {"$set": {"priority": PUBLIC_API_KEY_PRIORITY, "is_system": True}}
        )
```

2. **在 `services/mongo.py` 的 lifespan 中调用**
```python
async def lifespan(app):
    client = create_mongo_client()
    app.state.mongo_client = client
    app.state.mongo_db = get_database(client)
    
    # 初始化public API key
    from services.submissions import ensure_public_api_key
    try:
        await ensure_public_api_key(app.state.mongo_db)
        logger.info("Public API key initialized")
    except Exception as e:
        logger.warning("Failed to initialize public API key (will use fallback): %s", e)
        # 不阻止应用启动，使用代码常量作为fallback
    
    try:
        yield
    finally:
        client.close()
```

3. **Worker也需要初始化**
```python
# workers/run_worker.py
async def process_loop():
    client = create_mongo_client()
    db = get_database(client)
    
    # 初始化public API key（Worker启动时）
    from services.submissions import ensure_public_api_key
    try:
        await ensure_public_api_key(db)
    except Exception as e:
        logger.warning("Failed to initialize public API key: %s", e)
    
    try:
        # ... 现有逻辑
```

## 性能优化：缓存

如果需要优化性能，可以添加缓存：

```python
# 使用应用状态缓存
_public_api_key_initialized = False

async def ensure_public_api_key(db: AsyncIOMotorDatabase) -> None:
    global _public_api_key_initialized
    if _public_api_key_initialized:
        return
    
    # ... 初始化逻辑
    _public_api_key_initialized = True
```

## 总结

**推荐方案：数据库实现 + 应用启动时注入（lifespan）**

- ✅ 一致性：所有API key都在数据库中
- ✅ 可靠性：代码常量作为fallback
- ✅ 灵活性：可以通过数据库修改
- ✅ 自动化：应用启动时自动初始化
- ✅ 简单：实现简单，易于维护

