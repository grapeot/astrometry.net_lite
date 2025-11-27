# Job State Management System Design

## 概述

本文档描述 Job 状态管理系统的设计，用于解决 Worker 进程被意外终止时的状态恢复问题，并为前端提供实时的处理进度和日志信息。

**部署模式**：单机部署（API、Worker、MongoDB 在同一台机器上）

## 问题描述

当前架构中，Worker 进程可能被意外终止（kill），导致：
1. Job 执行到一半中断
2. 重启后状态不明确（可能某个步骤完成了，但没有继续后续步骤）
3. 无法恢复中断的 Job
4. 前端无法实时了解 Job 的处理进度

## 设计目标

1. **状态持久化**：每个阶段的状态都保存到文件系统
2. **可恢复性**：Worker 重启后可以继续未完成的 Job
3. **可观测性**：前端可以实时查看 Job 的当前阶段和日志输出
4. **简单性**：单机部署，避免过度设计

## 架构设计

### 混合方案：MongoDB + 文件系统

**核心思路**：
- **MongoDB**：存储最终状态（queued, solving, success, failure）和元数据 —— **权威数据源**
- **文件系统**：存储处理阶段、实时日志和恢复信息 —— **辅助信息**

**设计原则**：
1. **MongoDB 是权威状态源**：恢复时以 MongoDB 为主，文件系统为辅
2. **阶段性更新**：不追求百分比进度，只记录当前处理阶段
3. **实时日志**：前端可以通过轮询获取 solve-field 的实时输出

### 状态定义

#### MongoDB JobStatus（最终状态，不变）

```python
class JobStatus(str, Enum):
    queued = "queued"      # 已入队，等待处理
    solving = "solving"    # 正在处理（包含所有子阶段）
    success = "success"    # 成功完成
    failure = "failure"    # 失败
```

#### 文件系统 Stage（处理阶段）

```python
class ProcessingStage(str, Enum):
    started = "started"         # 刚开始处理
    solving = "solving"         # 运行 solve-field
    calibrating = "calibrating" # 提取校准信息
    annotating = "annotating"   # 生成 annotated image
    completed = "completed"     # 完成
    failed = "failed"           # 失败
```

### 文件结构

```
data/jobs/{job_id}/
├── status.json          # 当前阶段和状态（原子更新）
├── solve-field.log      # solve-field 实时输出日志
├── wcs.fits            # 输出文件
├── new-image.fits
├── annotated.jpg
└── ...
```

### status.json 格式

```json
{
  "job_id": 8,
  "stage": "solving",
  "message": "Running solve-field...",
  "started_at": "2025-11-26T18:26:02Z",
  "updated_at": "2025-11-26T18:26:15Z",
  "steps_completed": ["started"],
  "error": null
}
```

## 实现方案

### 1. StateManager 类

```python
# services/state_manager.py

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class StateManager:
    """管理 Job 的文件系统状态"""

    def __init__(self, job_dir: Path):
        self.job_dir = job_dir
        self.status_file = job_dir / "status.json"
        self.log_file = job_dir / "solve-field.log"

    def get_status(self) -> Optional[Dict[str, Any]]:
        """读取当前状态"""
        if not self.status_file.exists():
            return None

        try:
            content = self.status_file.read_text()
            return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return None

    def update_stage(
        self,
        stage: str,
        message: str = "",
        error: Optional[str] = None
    ):
        """原子更新阶段状态"""
        current = self.get_status() or {}

        # 更新已完成的步骤
        steps_completed = current.get("steps_completed", [])
        if current.get("stage") and current["stage"] not in steps_completed:
            if current["stage"] not in ["failed", "completed"]:
                steps_completed.append(current["stage"])

        new_status = {
            "job_id": current.get("job_id", self._extract_job_id()),
            "stage": stage,
            "message": message,
            "started_at": current.get("started_at", datetime.utcnow().isoformat() + "Z"),
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "steps_completed": steps_completed,
            "error": error,
        }

        self._atomic_write(self.status_file, json.dumps(new_status, indent=2))

    def append_log(self, content: str):
        """追加日志内容"""
        with open(self.log_file, "a") as f:
            f.write(content)

    def get_log(self, offset: int = 0) -> tuple[str, int]:
        """获取日志内容，返回 (内容, 新的offset)"""
        if not self.log_file.exists():
            return "", 0

        with open(self.log_file, "r") as f:
            f.seek(offset)
            content = f.read()
            new_offset = f.tell()

        return content, new_offset

    def _atomic_write(self, file_path: Path, content: str):
        """原子写入文件（使用临时文件 + rename）"""
        temp_file = file_path.with_suffix('.tmp')
        temp_file.write_text(content)
        temp_file.rename(file_path)

    def _extract_job_id(self) -> int:
        """从 job_dir 路径提取 job_id"""
        try:
            return int(self.job_dir.name)
        except ValueError:
            return 0
```

### 2. Worker 集成

```python
# workers/run_worker.py 中的 solve_job 修改

async def solve_job(db, job_id: int, payload: dict):
    job_dir = prepare_job_dir(job_id)
    state = StateManager(job_dir)

    # 1. 检查是否需要恢复
    file_status = state.get_status()
    if file_status and file_status["stage"] in ["solving", "calibrating", "annotating"]:
        # 检查 MongoDB 状态是否一致
        job = await job_service.get_job_by_job_id(db, job_id)
        if job and job.status == JobStatus.solving:
            # 尝试恢复
            await resume_job(db, job_id, file_status, state)
            return

    try:
        # 2. 更新 MongoDB（粗粒度）+ 创建文件状态
        await job_service.mark_job_started(db, job_id)
        state.update_stage("started", "Job started, preparing...")

        # 3. 运行 solve-field（流式输出日志）
        state.update_stage("solving", "Running solve-field...")

        proc = await asyncio.create_subprocess_exec(
            *cli_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        # 流式读取并保存日志
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            state.append_log(line.decode())

        await proc.wait()

        if proc.returncode != 0:
            error_msg = "solve-field failed with exit code " + str(proc.returncode)
            state.update_stage("failed", error_msg, error=error_msg)
            await job_service.update_job_status(db, job_id, JobStatus.failure, failure_reason=error_msg)
            return

        # 4. 提取校准信息
        state.update_stage("calibrating", "Extracting calibration data...")
        calibration = extract_calibration(...)

        # 5. 生成标注图像
        state.update_stage("annotating", "Generating annotated image...")
        annotated = await annotator.generate_annotation(...)

        # 6. 完成
        state.update_stage("completed", "Job completed successfully")
        await job_service.update_job_status(
            db, job_id, JobStatus.success,
            results={"calibration": calibration},
            objects_in_field=objects
        )

    except Exception as exc:
        error_msg = str(exc)
        state.update_stage("failed", error_msg, error=error_msg)
        await job_service.update_job_status(db, job_id, JobStatus.failure, failure_reason=error_msg)
        raise
```

### 3. 恢复机制

```python
async def resume_job(db, job_id: int, file_status: dict, state: StateManager):
    """恢复中断的 Job"""
    stage = file_status["stage"]
    job_dir = prepare_job_dir(job_id)

    if stage == "solving":
        # 检查 solve-field 是否完成（通过文件存在性判断）
        wcs_path = job_dir / "wcs.fits"
        if wcs_path.exists():
            # solve-field 完成了，继续后续步骤
            state.update_stage("calibrating", "Resuming: extracting calibration...")
            # ... 继续 calibrating 和 annotating
        else:
            # solve-field 未完成，重新运行
            state.update_stage("solving", "Restarting solve-field...")
            # ... 重新运行 solve-field

    elif stage == "calibrating":
        # 检查校准是否完成，决定是继续还是重新开始
        state.update_stage("calibrating", "Resuming calibration...")
        # ...

    elif stage == "annotating":
        # 检查标注是否完成
        state.update_stage("annotating", "Resuming annotation...")
        # ...


async def recover_incomplete_jobs(db):
    """Worker 启动时恢复所有未完成的 Job"""
    # 查询 MongoDB 中所有 status=solving 的 Job
    cursor = db["jobs"].find({
        "status": JobStatus.solving.value,
        "finished_at": None
    })

    async for doc in cursor:
        job_id = doc["job_id"]
        job_dir = prepare_job_dir(job_id)
        state = StateManager(job_dir)
        file_status = state.get_status()

        if file_status:
            # 有文件状态，尝试恢复
            await resume_job(db, job_id, file_status, state)
        else:
            # 没有文件状态，重置为 queued 重新处理
            logger.warning(f"Job {job_id} has no file status, resetting to queued")
            await job_service.update_job_status(db, job_id, JobStatus.queued)
```

### 4. API 接口

#### 获取 Job 列表（前端瀑布流）

```python
@router.get("/jobs/list")
async def list_jobs(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    db = Depends(get_db)
):
    """获取 Job 列表，组合 MongoDB 和文件系统数据"""
    skip = (page - 1) * limit

    query = {}
    if status:
        query["status"] = status

    cursor = db["jobs"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    jobs = [Job(**doc) async for doc in cursor]

    result_jobs = []
    for job in jobs:
        job_data = {
            "job_id": job.job_id,
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "has_annotated_image": bool(job.artifacts.get("annotated")),
        }

        # 添加图片 URL
        if job_data["has_annotated_image"]:
            job_data["annotated_image_url"] = f"/annotated_display/{job.job_id}"

        # 如果是 solving 状态，从文件系统读取阶段信息
        if job.status == JobStatus.solving:
            job_dir = prepare_job_dir(job.job_id)
            state = StateManager(job_dir)
            file_status = state.get_status()
            if file_status:
                job_data["stage"] = file_status.get("stage")
                job_data["message"] = file_status.get("message")

        result_jobs.append(job_data)

    total = await db["jobs"].count_documents(query)

    return {
        "status": "success",
        "jobs": result_jobs,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": (skip + limit) < total
        }
    }
```

#### 获取 Job 详情

```python
@router.get("/jobs/{job_id}/detail")
async def get_job_detail(job_id: int, db = Depends(get_db)):
    """获取 Job 完整详情"""
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = {
        "job_id": job.job_id,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "failure_reason": job.failure_reason,
        "has_annotated_image": bool(job.artifacts.get("annotated")),
    }

    # 添加图片 URL
    if result["has_annotated_image"]:
        result["annotated_image_url"] = f"/annotated_display/{job_id}"

    # 获取原图 URL（通过 submission）
    submission = await submission_service.get_submission(db, str(job.submission_id))
    if submission:
        result["original_image_url"] = f"/api/files/original/{job_id}"

    # 添加校准信息
    if job.results.get("calibration"):
        result["calibration"] = job.results["calibration"]

    # 添加天体列表
    if job.objects_in_field:
        result["objects_in_field"] = job.objects_in_field

    # 添加下载链接
    artifacts = {}
    for artifact_type, path in job.artifacts.items():
        artifacts[artifact_type] = f"/{artifact_type}_file/{job_id}"
    result["artifacts"] = artifacts

    # 如果是 solving 状态，添加阶段信息
    if job.status == JobStatus.solving:
        job_dir = prepare_job_dir(job_id)
        state = StateManager(job_dir)
        file_status = state.get_status()
        if file_status:
            result["stage"] = file_status.get("stage")
            result["message"] = file_status.get("message")

    return {"status": "success", "job": result}
```

#### 获取实时日志（轮询用）

```python
@router.get("/jobs/{job_id}/log")
async def get_job_log(
    job_id: int,
    offset: int = 0,
    db = Depends(get_db)
):
    """获取 Job 的实时日志（支持增量获取）"""
    job = await job_service.get_job_by_job_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dir = prepare_job_dir(job_id)
    state = StateManager(job_dir)

    # 获取状态
    file_status = state.get_status()

    # 获取增量日志
    log_content, new_offset = state.get_log(offset)

    return {
        "status": "success",
        "job_status": job.status.value,
        "stage": file_status.get("stage") if file_status else None,
        "message": file_status.get("message") if file_status else None,
        "log": log_content,
        "offset": new_offset,
        "is_running": job.status == JobStatus.solving
    }
```

## 前端设计

### 页面结构

#### 1. 首页：Job 瀑布流

**URL**: `/` 或 `/jobs`

```
┌─────────────────────────────────────────┐
│  Header: "Astrometry.net Lite"          │
├─────────────────────────────────────────┤
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐       │
│  │Job 1│ │Job 2│ │Job 3│ │Job 4│       │
│  │Img  │ │Img  │ │Img  │ │Img  │       │
│  └─────┘ └─────┘ └─────┘ └─────┘       │
│  ... (无限滚动)                          │
└─────────────────────────────────────────┘
```

#### 2. Job 详情页

**URL**: `/jobs/{job_id}`

**进行中状态**：
```
┌─────────────────────────────────────────┐
│  Header: "Job #8"                       │
├─────────────────────────────────────────┤
│  Status: [solving] Stage: calibrating   │
│  Message: Extracting calibration data...│
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  Log Output:                       │ │
│  │  > Reading input file...           │ │
│  │  > Solving...                      │ │
│  │  > Field 1 solved...               │ │
│  │  (实时更新)                         │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**完成状态**：
```
┌─────────────────────────────────────────┐
│  Header: "Job #8"                       │
├─────────────────────────────────────────┤
│  ┌───────────────────────────────────┐ │
│  │    Annotated Image (大图)          │ │
│  └───────────────────────────────────┘ │
│  Objects: [NGC 3628] [M 66] [M 65]     │
│  Downloads: [WCS] [FITS] [Corr] [KML]  │
│  ┌───────────────────────────────────┐ │
│  │  Log (可折叠)                       │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### 前端轮询逻辑

```typescript
// hooks/useJobDetail.ts
export function useJobDetail(jobId: number) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [log, setLog] = useState<string>("");
  const [logOffset, setLogOffset] = useState<number>(0);

  // 初始加载详情
  useEffect(() => {
    fetch(`/api/jobs/${jobId}/detail`)
      .then(res => res.json())
      .then(data => setJob(data.job));
  }, [jobId]);

  // 如果是 solving 状态，每 10 秒轮询日志
  useEffect(() => {
    if (job?.status !== 'solving') return;

    const poll = async () => {
      const res = await fetch(`/api/jobs/${jobId}/log?offset=${logOffset}`);
      const data = await res.json();

      if (data.log) {
        setLog(prev => prev + data.log);
        setLogOffset(data.offset);
      }

      // 更新状态
      if (data.job_status !== 'solving') {
        // Job 完成，刷新详情
        const detailRes = await fetch(`/api/jobs/${jobId}/detail`);
        const detailData = await detailRes.json();
        setJob(detailData.job);
      } else {
        setJob(prev => prev ? {
          ...prev,
          stage: data.stage,
          message: data.message
        } : null);
      }
    };

    const interval = setInterval(poll, 10000); // 10 秒轮询
    poll(); // 立即执行一次

    return () => clearInterval(interval);
  }, [job?.status, jobId, logOffset]);

  return { job, log };
}
```

### 前端组件结构

```
frontend/src/
├── pages/
│   ├── JobGrid.tsx          # 瀑布流首页
│   └── JobDetail.tsx        # Job 详情页
├── components/
│   ├── JobCard.tsx          # Job 卡片
│   ├── JobStatus.tsx        # 状态显示（badge + stage）
│   ├── LogViewer.tsx        # 日志查看器（自动滚动）
│   ├── ObjectsList.tsx      # 天体列表
│   └── DownloadLinks.tsx    # 下载链接
├── api/
│   └── jobs.ts              # API 调用封装
└── hooks/
    ├── useJobList.ts        # 瀑布流 Hook
    └── useJobDetail.ts      # 详情 + 轮询 Hook
```

## 实施步骤

### Phase 1: 状态管理基础

1. 创建 `services/state_manager.py`
2. 修改 `services/solver_bridge.py`，集成 StateManager
3. 实现流式日志输出
4. 添加恢复机制

### Phase 2: API 接口

1. 实现 `GET /api/jobs/list`
2. 实现 `GET /api/jobs/{job_id}/detail`
3. 实现 `GET /api/jobs/{job_id}/log`
4. 实现 `GET /api/files/original/{job_id}`

### Phase 3: 前端实现

1. 实现 JobGrid 页面
2. 实现 JobDetail 页面
3. 实现日志轮询
4. 响应式优化

## 状态转移规则

### MongoDB JobStatus

```
queued ──────► solving ──────► success
                  │
                  └──────────► failure
```

### 文件系统 Stage

```
started ──► solving ──► calibrating ──► annotating ──► completed
              │              │               │
              └──────────────┴───────────────┴──────► failed
```

### 状态同步规则

| 时机 | MongoDB | 文件系统 |
|------|---------|---------|
| Job 创建 | `status=queued` | 无 |
| Worker 开始 | `status=solving` | `stage=started` |
| 运行 solve-field | 不变 | `stage=solving` + 日志 |
| 提取校准 | 不变 | `stage=calibrating` |
| 生成标注 | 不变 | `stage=annotating` |
| 成功完成 | `status=success` | `stage=completed` |
| 失败 | `status=failure` | `stage=failed` |

## 注意事项

1. **MongoDB 是权威状态源**：恢复时以 MongoDB 为主，文件系统只提供阶段信息
2. **原子写入**：使用临时文件 + rename 确保文件写入的原子性
3. **日志追加**：日志文件使用追加模式，支持增量读取
4. **单机部署**：不考虑分布式文件锁，fcntl 足够
5. **轮询间隔**：前端使用 10 秒轮询，平衡实时性和服务器压力
