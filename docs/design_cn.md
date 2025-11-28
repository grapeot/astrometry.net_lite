# Astrometry Lite - 系统设计文档

> English Version: [design_en.md](./design_en.md)

## 概述

**Astrometry Lite** 是 [astrometry.net](https://astrometry.net) 板解（plate solving）服务的现代化重新实现。原版 astrometry.net 诞生于 2010 年左右，它利用几何不变性和巧妙的启发式算法，实现了快速、可靠的盲解板解，彻底革新了天文图像校准领域。

然而，原版实现使用的是那个年代的技术——Django 单体应用、WSGI/FastCGI 部署、服务端模板渲染、Python 2 兼容层。这个项目想要回答一个问题：**如果我们在 2025 年重新构建 astrometry.net，它会是什么样子？**

Astrometry Lite 的答案是：
- **FastAPI** 提供异步、高性能的 API
- **React + Vite** 构建现代化前端
- **MongoDB** 实现灵活的文档存储
- **文件系统状态** 支持实时任务追踪

**Live Demo:** [https://astrometry.yage.ai/](https://astrometry.yage.ai/)

## 新旧实现对比

### 原版实现（net/ 目录）

原版 astrometry.net 实现（保留在 `net/` 目录中）展示了 2009-2012 年代的 Web 开发风格：

| 方面 | 原版实现 |
|------|---------|
| **框架** | Django 1.x 单体应用 |
| **部署** | WSGI/FastCGI (Apache mod_wsgi) |
| **数据库** | PostgreSQL + Django ORM |
| **前端** | 服务端 Django 模板渲染 |
| **API 风格** | 手工 JSON 序列化，`text/plain` 响应 |
| **Python** | Python 2/3 混合，充满 `__future__` 导入 |
| **架构** | 单个 Django 应用，14 个视图文件，1398 行的 models.py |
| **上传处理** | 手动构造 multipart 边界 |
| **认证** | Django sessions + 社交登录 |

**遗留代码的特征：**
- 基于函数的视图，正则表达式 URL 路由
- 自定义 `python2json`/`json2python` 转换函数
- API、前端、管理混在一起的单体结构
- 通过 Python 模块导入外部密钥
- 严重依赖系统路径（`/data/`、`/usr/local/`）

### Astrometry Lite（本项目）

| 方面 | 现代实现 |
|------|---------|
| **框架** | FastAPI（异步、类型安全） |
| **部署** | Uvicorn ASGI 服务器 |
| **数据库** | MongoDB + Motor（异步驱动） |
| **前端** | React + Vite + TypeScript（SPA） |
| **API 风格** | OpenAPI/Swagger，规范 JSON，Pydantic 验证 |
| **Python** | 仅 Python 3.12+ |
| **架构** | 微服务：独立的 API、Worker、Frontend（开发环境）<br>统一服务：后端 serve 前端（生产环境） |
| **上传处理** | FastAPI 原生 multipart 支持 |
| **认证** | 简单 API key（单租户） |
| **静态文件** | FastAPI StaticFiles + SPA 路由支持 |
| **Docker** | 多阶段构建，前端构建集成到后端镜像 |

## 系统架构

### 开发环境架构

```
┌─────────────────────────────────────────────────────────────┐
│                     前端 (React + Vite Dev Server)          │
│  端口: 5173                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  JobGrid    │  │ JobDetail   │  │  Console (需认证)    │  │
│  │  (公开)     │  │ (公开)      │  │  (上传/管理)         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP (CORS)
┌────────────────────────────▼────────────────────────────────┐
│                    FastAPI 后端                              │
│  端口: 8002                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ Legacy API     │  │ Frontend API   │  │ 文件路由      │  │
│  │ /api/*         │  │ /api/jobs/*    │  │ /wcs_file/*  │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└───────┬─────────────────────┬───────────────────┬───────────┘
        │                     │                   │
┌───────▼─────────┐  ┌────────▼────────┐  ┌──────▼──────────┐
│    MongoDB      │  │    文件系统      │  │   Worker        │
│  - api_keys     │  │  - uploads/     │  │  - solve-field  │
│  - submissions  │  │  - jobs/{id}/   │  │  - annotator    │
│  - jobs         │  │    - wcs.fits   │  │                 │
│  - queue        │  │    - status.json│  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 生产环境架构（简化）

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI 后端 (统一服务)                    │
│  端口: 8002                                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  静态文件服务 (frontend/dist)                            │ │
│  │  - /assets/* (JS, CSS)                                  │ │
│  │  - / (SPA 路由，返回 index.html)                         │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ Legacy API     │  │ Frontend API   │  │ 文件路由      │  │
│  │ /api/*         │  │ /api/jobs/*    │  │ /wcs_file/*  │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└───────┬─────────────────────┬───────────────────┬───────────┘
        │                     │                   │
┌───────▼─────────┐  ┌────────▼────────┐  ┌──────▼──────────┐
│    MongoDB      │  │    文件系统      │  │   Worker        │
│  - api_keys     │  │  - uploads/     │  │  - solve-field  │
│  - submissions  │  │  - jobs/{id}/   │  │  - annotator    │
│  - jobs         │  │    - wcs.fits   │  │                 │
│  - queue        │  │    - status.json│  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

**生产环境特点：**
- 后端容器内置前端构建产物（`frontend/dist`）
- FastAPI 自动 serve 静态文件和 SPA 路由
- 前端使用相对路径 `/api` 调用后端 API
- 单一端口（8002）提供完整服务
- 无需独立的 nginx 或前端容器

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | FastAPI + Uvicorn |
| 数据库 | MongoDB 7+（Motor 异步驱动） |
| 队列 | MongoDB（queue_messages 集合） |
| 求解器 | Astrometry.net CLI（Homebrew） |
| 前端 | React 19 + Vite 7 + TypeScript |
| 图像处理 | Pillow, Astropy |
| 静态文件服务 | FastAPI StaticFiles（生产环境） |
| 部署 | Docker + Docker Compose（多阶段构建） |

## 数据模型

### MongoDB 集合

**api_keys**
```javascript
{
  _id: ObjectId,
  apikey: "test-key-12345",  // 唯一索引
  email: "user@example.com",
  created_at: ISODate
}
```

**submissions**
```javascript
{
  _id: ObjectId,
  api_key: "test-key-12345",
  original_filename: "image.jpg",
  stored_path: "./data/uploads/uuid-image.jpg",
  upload_args: { scale_units: "arcsecperpix", ... },
  status: "queued|processing|success|failure",
  jobs: [1, 2, 3],
  created_at: ISODate,
  processing_started: ISODate,
  processing_finished: ISODate
}
```

**jobs**
```javascript
{
  _id: ObjectId,
  job_id: 123,  // 自增唯一 ID
  submission_id: ObjectId,
  status: "queued|solving|success|failure",
  failure_reason: null,
  results: {
    original_filename: "image.jpg",
    calibration: { ra, dec, pixscale, orientation, radius, ... }
  },
  artifacts: {
    wcs: "./data/jobs/123/wcs.fits",
    new_fits: "./data/jobs/123/new.fits",
    annotated: "./data/jobs/123/annotated.jpg"
  },
  objects_in_field: ["M31", "NGC 224", ...],
  annotations: [{ text: "M31" }, ...],
  created_at: ISODate,
  started_at: ISODate,
  finished_at: ISODate
}
```

### 文件系统结构

```
data/
├── uploads/           # 原始上传文件
│   └── uuid-image.jpg
└── jobs/
    └── {job_id}/
        ├── status.json      # 实时处理状态
        ├── solve-field.log  # CLI 输出日志
        ├── wcs.fits         # 世界坐标系统
        ├── new.fits         # 带 WCS 头的 FITS
        ├── corr.fits        # 星点相关数据
        └── annotated.jpg    # 标注图像
```

## 任务状态管理

### 混合状态模型

系统采用混合方案：
1. **MongoDB（权威源）**：最终任务状态
2. **文件系统（进度）**：实时阶段和日志

### 状态流转

```
MongoDB 状态:    queued ──► solving ──► success
                               │
                               └──────► failure

文件系统阶段:   started ──► solving ──► calibrating ──► annotating ──► completed
```

### status.json 格式

```json
{
  "job_id": 123,
  "stage": "solving",
  "message": "Running solve-field...",
  "started_at": "2025-11-26T18:26:02Z",
  "updated_at": "2025-11-26T18:26:15Z",
  "steps_completed": ["started"],
  "error": null
}
```

## API 接口

### Legacy API（需认证）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/login` | POST | API key 认证 |
| `/api/upload` | POST | 文件上传 |
| `/api/url_upload` | POST | URL 上传 |
| `/api/submissions/{id}` | GET/POST | 提交状态 |
| `/api/jobs/{id}` | GET/POST | 任务状态 |
| `/api/jobs/{id}/calibration` | GET/POST | 校准数据 |
| `/api/jobs/{id}/info` | GET/POST | 完整信息 |
| `/api/myjobs/` | GET/POST | 用户任务列表 |

### Frontend API（公开）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/jobs/list` | GET | 分页任务列表 |
| `/api/jobs/{id}/detail` | GET | 任务详情 |
| `/api/jobs/{id}/log` | GET | 实时日志 |
| `/api/files/original/{id}` | GET | 原始图像 |

### 文件下载

| 端点 | 描述 |
|------|------|
| `/wcs_file/{id}` | WCS FITS 文件 |
| `/new_fits_file/{id}/` | 求解后的 FITS |
| `/corr_file/{id}` | 相关数据 |
| `/annotated_display/{id}` | 标注图像 |

## 前端页面

| 路径 | 页面 | 描述 |
|------|------|------|
| `/` | JobGrid | 公开的任务画廊 |
| `/jobs/:id` | JobDetail | 任务详情 + 实时日志 |
| `/console` | Console | 需认证的上传界面 |

## 快速开始

### 开发环境

```bash
# 1. 启动 MongoDB
./scripts/start_mongodb.sh

# 2. 初始化 API Key
PYTHONPATH=. python scripts/seed_api_key.py test-key-12345 test@example.com

# 3. 启动后端
./scripts/start_backend.sh

# 4. 启动 Worker
./scripts/start_worker.sh

# 5. 启动前端（开发服务器）
cd frontend && npm run dev
```

**访问地址：**
- API: http://127.0.0.1:8002
- 前端: http://localhost:5173

### 生产环境

#### 方式一：使用 Docker Compose（推荐）

```bash
# 构建并启动所有服务（包括前端构建）
./scripts/start_backend_prod.sh

# 或者手动执行
docker-compose -f docker-compose.prod.yml up -d --build
```

**访问地址：**
- 统一入口: http://localhost:8002（前端和 API）

#### 方式二：本地部署

```bash
# 1. 构建前端
cd frontend
VITE_API_BASE=/api npm run build

# 2. 启动后端（会自动serve前端）
./scripts/start_backend.sh

# 3. 启动 Worker
./scripts/start_worker.sh
```

**访问地址：**
- 统一入口: http://127.0.0.1:8002（前端和 API）

## 配置

所有配置选项见 `.env` 文件，包括 MongoDB URI、CLI 路径和功能开关。

## 项目结构

```
astrometry.net_web_server/
├── api/                 # FastAPI 后端
│   ├── main.py          # 应用入口（包含静态文件服务）
│   ├── routes/
│   │   ├── legacy.py    # 原版 API 兼容
│   │   └── frontend.py  # 公开前端 API
├── services/            # 业务逻辑
│   ├── solver_bridge.py # CLI 集成
│   ├── state_manager.py # 文件系统状态
│   └── annotator/       # 图像标注
├── workers/             # 后台处理
├── frontend/            # React 应用
│   ├── src/
│   │   ├── pages/       # JobGrid, JobDetail
│   │   └── hooks/       # useJobList, useJobDetail
│   └── dist/            # 构建产物（生产环境）
├── domain/              # 数据模型
├── scripts/             # 工具脚本
│   └── start_backend_prod.sh  # 生产环境启动脚本
├── Dockerfile           # 多阶段构建（包含前端构建）
├── docker-compose.prod.yml  # 生产环境配置
└── docs/                # 文档
```

**生产环境构建说明：**
- `Dockerfile` 使用多阶段构建：
  1. `base` stage: 构建 Python 后端
  2. `frontend-builder` stage: 构建前端（使用 `VITE_API_BASE=/api`）
  3. 最终 stage: 合并后端和前端构建产物到 `frontend/dist`
- 后端容器包含 `frontend/dist`，FastAPI 自动 serve 静态文件

## 未实现的功能

以下原版功能未实现：
- SDSS/GALEX 图像叠加
- KMZ 生成（需要 wcs2kml）
- 多租户用户管理
- 社交登录

这些端点会返回友好的错误信息。
