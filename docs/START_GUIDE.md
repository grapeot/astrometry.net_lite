# Astrometry Lite 服务启动指南

本文档提供完整的服务启动步骤和测试方法。

## 前置准备

### 1. 环境要求
- Python 3.12+
- MongoDB 7+（本地或 Atlas）
- Astrometry.net CLI（通过 Homebrew 安装）
- Node.js 和 npm（用于前端）

### 2. 安装依赖

#### Python 依赖
```bash
# 激活虚拟环境（如果使用 uv）
source venv/bin/activate

# 安装 Python 依赖（如果还未安装）
uv pip install -r <(python - <<'PY'
from pathlib import Path
from tomllib import load
py = Path('pyproject.toml')
data = load(py.open('rb'))
print('\n'.join(data['project']['dependencies'] + data['project']['optional-dependencies']['dev']))
PY
)
```

#### 前端依赖
```bash
cd frontend
npm install
cd ..
```

### 3. 配置环境变量

创建或编辑 `.env` 文件（参考 `core/config.py` 中的默认值）：

```bash
# MongoDB 配置
MONGODB_URI=mongodb://localhost:27017
MONGODB_DBNAME=astrometry_dev

# API 配置
API_HOST=127.0.0.1
API_PORT=8002

# 数据目录
DATA_ROOT=./data
ASTROMETRY_INDEX_DIR=./astrometry_indexes
JOB_OUTPUT_DIR=./data/jobs
UPLOAD_CACHE_DIR=./data/uploads

# CLI 路径（Homebrew 默认路径）
SOLVE_FIELD_BIN=/opt/homebrew/bin/solve-field
AUGMENT_XYLIST_BIN=/opt/homebrew/bin/augment-xylist
ASTROMETRY_ENGINE_BIN=/opt/homebrew/bin/astrometry-engine

# 队列配置
QUEUE_VISIBILITY_TIMEOUT_SECONDS=300
ENABLE_KMZ=false

# 前端 CORS（可选）
FRONTEND_ORIGIN=http://localhost:5173
```

## 启动步骤

### 步骤 1: 启动 MongoDB

```bash
# 使用项目提供的脚本启动本地 MongoDB
./scripts/start_mongodb.sh

# 或者手动启动
mongod --dbpath ./mongodb_data --port 27017
```

**验证 MongoDB 运行：**
```bash
mongosh mongodb://localhost:27017
```

### 步骤 2: 初始化 API Key

```bash
# 创建一个测试用的 API Key
PYTHONPATH=. python scripts/seed_api_key.py test-key-12345 test@example.com

# 或者使用其他 key
PYTHONPATH=. python scripts/seed_api_key.py your-secret-key your@email.com
```

### 步骤 3: 启动后端 API

```bash
# 使用脚本启动（推荐）
./scripts/start_backend.sh

# 或者手动启动
uvicorn api.main:app --reload --host 127.0.0.1 --port 8002
```

**验证 API 运行：**
```bash
curl http://127.0.0.1:8002/
# 应该返回: {"message":"Astrometry Lite API"}
```

### 步骤 4: 启动 Worker（处理队列任务）

```bash
# 使用脚本启动（后台运行）
./scripts/start_worker.sh

# 查看 worker 日志
tail -f logs/worker.log

# 停止 worker（如果需要）
kill $(cat logs/worker.pid)
```

### 步骤 5: 启动前端（可选）

```bash
# 使用脚本启动
./scripts/start_frontend.sh

# 或者手动启动
cd frontend
npm run dev
```

前端默认运行在 `http://localhost:5173`

## 完整启动流程（一键启动）

如果你需要同时启动所有服务，可以打开多个终端窗口：

**终端 1 - MongoDB:**
```bash
./scripts/start_mongodb.sh
```

**终端 2 - 后端 API:**
```bash
./scripts/start_backend.sh
```

**终端 3 - Worker:**
```bash
./scripts/start_worker.sh
```

**终端 4 - 前端（可选）:**
```bash
./scripts/start_frontend.sh
```

## 测试服务

### 快速测试（不等待 Job 完成）

```bash
# 使用默认配置
python scripts/test_service.py --quick

# 指定 API Key 和图片
python scripts/test_service.py --quick --apikey test-key-12345 --file test.jpg
```

### 完整测试（等待 Job 完成并下载文件）

```bash
# 使用默认配置
python scripts/test_service.py

# 自定义配置
python scripts/test_service.py \
  --api-base http://127.0.0.1:8002/api \
  --apikey test-key-12345 \
  --file test.jpg \
  --poll 3.0 \
  --timeout 300
```

### 测试参数说明

- `--api-base`: API 基础 URL（默认: `http://127.0.0.1:8002/api`）
- `--apikey`: API Key（默认: `test-key-12345`）
- `--file`: 测试图片路径（默认: `test.jpg`）
- `--poll`: 轮询间隔秒数（默认: 3.0）
- `--timeout`: 超时时间秒数（默认: 300）
- `--quick`: 快速测试模式（跳过轮询和下载）

### 测试内容

测试脚本会验证以下功能：

1. ✅ **登录** - API Key 认证
2. ✅ **上传** - 图片上传和 Job 创建
3. ✅ **轮询** - 等待 Job 完成（完整测试模式）
4. ✅ **查询端点** - calibration, info, annotations 等
5. ✅ **文件下载** - WCS, FITS, CORR, Annotated 文件
6. ✅ **Submission 状态** - 查询 submission 信息
7. ✅ **不支持功能** - SDSS/GALEX overlay 的正确错误响应

## 常见问题

### MongoDB 连接失败

```bash
# 检查 MongoDB 是否运行
ps aux | grep mongod

# 检查端口是否被占用
lsof -i :27017

# 检查 MongoDB 日志
tail -f mongodb.log
```

### API 启动失败

```bash
# 检查端口是否被占用（默认 8002）
lsof -i :8002

# 检查日志
tail -f logs/backend.log

# 检查环境变量
cat .env
```

### Worker 不处理任务

```bash
# 检查 worker 是否运行
ps aux | grep run_worker

# 查看 worker 日志
tail -f logs/worker.log

# 检查队列中是否有任务
mongosh mongodb://localhost:27017/astrometry_dev
> db.queue_messages.find({completed_at: null})
```

### 图片求解失败

1. 确认 `solve-field` 命令可用：
   ```bash
   /opt/homebrew/bin/solve-field --help
   ```

2. 确认 index files 存在：
   ```bash
   ls -la astrometry_indexes/ | head
   ```

3. 检查 worker 日志中的错误信息：
   ```bash
   tail -f logs/worker.log
   ```

## 停止服务

```bash
# 停止 MongoDB
./scripts/stop_mongodb.sh
# 或按 Ctrl+C（如果在终端中运行）

# 停止后端 API
# 按 Ctrl+C（如果在终端中运行）

# 停止 Worker
kill $(cat logs/worker.pid)

# 停止前端
# 按 Ctrl+C（如果在终端中运行）
```

## 下一步

- 查看 `docs/dev_plan.md` 了解项目架构
- 查看 `docs/working_log.md` 了解开发进度
- 查看 `README.md` 了解项目概述

