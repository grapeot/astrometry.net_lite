# Astrometry.net 简化版重构计划（工作稿）

_最后更新：2025-11-07_

## 背景
- 代码参考范围：只需保留 `net/` 目录（API 语义、模型、求解脚本）以及 `test_installation.py`（验证 brew 版 CLI 是否可用）；其余子目录可忽略。
- 我们要交付一个“轻量可维护”的自有实现：FastAPI + React，后端直接调用 brew 安装的 Astrometry CLI，数据持久层改用 **MongoDB**（取代 SQLite），Pydantic 负责数据校验。
- 用户模型极简：系统整体视为单租户，只维护一个逻辑用户但允许多个 API key。无需 Django/Firebase/社交登录。如需扩展多租户，可在 MongoDB 中增加 `users` 集合并与 `api_keys` 建立关联。

## 兼容性要求
1. **协议兼容**：沿用原 API URL/JSON 结构（`request-json` 包装、`session` token、下载路径），保证 `net/client/client.py` 及现有脚本零修改即能调用。
2. **命令行兼容**：调用与原项目相同的 CLI（通过 brew 安装），保持 `net/process_submissions.py` 中的参数逻辑不变。
3. **制品兼容**：继续输出 `wcs.fits`/`new_fits_file`/`corr.fits` 等文件，并通过 `/wcs_file/<jobid>` 等路径下载。

## 技术决策
- **后端**：FastAPI + Pydantic + `motor`(async MongoDB 驱动)。
- **数据库**：MongoDB（云托管或本地），集合示例：`api_keys`, `submissions`, `jobs`, `artifacts`, `queue_messages`。
  - `.env` 暴露 `MONGODB_URI`, `MONGODB_DBNAME`，可含用户名/密码或 Atlas connection string。
- **队列**：改为 MongoDB-backed 队列：`queue_messages` 集合存储 job payload + 状态，API 写入即持久化，worker 通过 `findOneAndUpdate` 原子领取任务，保证重启后可恢复；内存层仅保留轻量 cache（可选）。
- **认证**：仅依赖自管 API key。`/api/login` 验证 `api_keys` 集合并返回 session（直接复用 key 以保持兼容）。
- **前端**：React (Vite + TypeScript)，最小可用界面：登录（API key 输入）、上传、job 列表、job 详情。
- **存储**：上传/制品仍落地到可配置目录（默认 `./data/jobs/<jobid>`），MongoDB 仅保存元数据/路径。Astrometry index files 已预下载在项目根目录的 `./astrometry_indexes/`，通过环境变量 `ASTROMETRY_INDEX_DIR` 指向该目录即可，无需重复拉取。
- **配置**：Pydantic Settings（.env）提供 CLI 路径、数据目录、Mongo 连接信息。

### CLI 默认路径（来自 brew 安装）
- `solve-field`: `/opt/homebrew/bin/solve-field`
- `augment-xylist`: `/opt/homebrew/bin/augment-xylist`
- `astrometry-engine`: `/opt/homebrew/bin/astrometry-engine`
> 这些路径写入默认配置；通过 `.env` 的 `SOLVE_FIELD_BIN`, `AUGMENT_XYLIST_BIN`, `ASTROMETRY_ENGINE_BIN` 覆盖。

#### 实测命令（`test.jpg`）
```
/opt/homebrew/bin/solve-field \
  --overwrite \
  --dir data/manual \
  --temp-dir data/manual \
  --index-dir astrometry_indexes \
  --wcs data/manual/test.wcs.fits \
  --new-fits data/manual/test.new.fits \
  --corr data/manual/test.corr.fits \
  --rdls data/manual/test.rdls.fits \
  --match data/manual/test.match.fits \
  --kmz data/manual/test.sky.kmz \
  test.jpg
```
- 默认额外产出：`test.solved`, `test.axy`, `test-indx.png`, `test-ngc.png`, `test-objs.png` 等，可直接挂载至 `/annotated_display` 或作为调试制品。
- 求解日志包含中心坐标、像素尺度、旋转角、命中星体列表等，可解析生成 `/jobs/{id}/calibration`、`/jobs/{id}/objects_in_field` 响应。

### MongoDB 本地启动（测试用）
- **安装**：`brew tap mongodb/brew && brew install mongodb-community`
- **Binary 路径**：`/opt/homebrew/bin/mongod`
- **临时启动**：使用项目根目录的 `scripts/start_mongodb.sh` 脚本
  - 数据目录：`./mongodb_data`（项目根目录）
  - 端口：`27017`
  - 连接字符串：`mongodb://localhost:27017`
  - 停止：运行 `scripts/stop_mongodb.sh` 或按 Ctrl+C
- **生产部署**：可使用 Docker 或 MongoDB Atlas

### 仍需提供/确认的信息
- 明确 Mongo 实例的长期托管策略（自管/Atlas）及多环境（dev/staging/prod）连接串。
- 下载注释图（annotated image）的原始输出规格（PNG/JPEG？带透明度？）以便 CLI worker 正确调用绘图脚本。
- CLI 产出的校准/overlay：决定是否引入 astropy/astrometry util 解析 WCS，还是提供自定义 lightweight 解析以填充 `/jobs/*/calibration` 以及 `sdss_image_for_wcs`、`galex_image_for_wcs`。

## 目标架构
```
project/
├─ api/
│  ├─ main.py
│  ├─ deps.py           # Mongo client、认证、队列依赖
│  ├─ routes/
│  │   ├─ legacy.py     # /api/*、/wcs_file/* 兼容层
│  │   └─ admin.py      # API key/健康检查
│  └─ schemas/
├─ services/
│  ├─ submissions.py    # 写 Mongo, 投递队列
│  ├─ jobs/
│  │   ├─ queue_backend.py
│  │   ├─ in_memory.py
│  │   └─ worker.py     # worker 读 Mongo，写状态
│  ├─ artifacts.py
│  └─ solver_bridge.py
├─ domain/
│  ├─ models.py         # Pydantic/Mongo 嵌套模型
│  └─ enums.py
├─ frontend/
└─ tests/
   ├─ integration/test_client_compat.py
   ├─ unit/test_solver_bridge.py
   └─ unit/test_queue_backend.py
```

## 后端流程（结合 Mongo）
1. `/api/login`：从 `api_keys` 集合读取 key，返回 `{status:'success', session:<key>}`。
2. `/api/upload`：写 `submissions` 文档（含 metadata、文件路径、创建时间），写 `jobs` 文档（status=queued），并往 `queue_messages` 集合插入待处理任务。
3. Worker：轮询 Mongo（或使用 change stream）领取队列任务 → 调 CLI → 更新 `jobs` 文档（status、开始/结束时间、错误信息）、`artifacts` 文档（结果文件路径），并写回 `queue_messages` 完成态。
4. 查询/下载接口：从 Mongo 读取 `submissions`/`jobs`，构建 legacy JSON；`/wcs_file/*` 等路由直接读取本地文件或流式返回。
5. 前端：调用 API 获取 Mongo 状态，与 CLI 输出文件联动刷新 UI。

## API 兼容范围（基于 `net/client/client.py`）
- Auth & submissions：`/api/login`, `/api/upload`, `/api/url_upload`, `/api/submissions/<id>`, `/api/submissions/<id>/jobs`, `/api/submission_images`。
- Job lifecycle：`/api/jobs/<id>`, `/api/jobs/<id>/calibration`, `/api/jobs/<id>/tags`, `/api/jobs/<id>/machine_tags`, `/api/jobs/<id>/objects_in_field`, `/api/jobs/<id>/annotations`, `/api/jobs/<id>/info`, `/api/myjobs/`, `/api/jobs_by_tag`。
- Visualization：`/api/sdss_image_for_wcs`, `/api/galex_image_for_wcs`, `/api/jobs/<id>/annotations`（JSON）以及新增 `/annotated_display/<jobid>` （PNG/JPEG 下载）。
- 文件制品：`/wcs_file/<jobid>`, `/kml_file/<jobid>/`, `/new_fits_file/<jobid>/`, `/corr_file/<jobid>` 等公开路由。

> 以上列表将记录在 `docs/working_log.md` 中，随功能落地逐条打勾并注明测试覆盖。

## 开发里程碑（沿用之前结构，替换到 Mongo）
1. **M1：FastAPI 骨架 & Mongo 接入**
   - 初始化 FastAPI + motor，封装 `get_mongo_client` 依赖。
   - 定义集合 schema（Pydantic Models + 索引：`api_keys.apikey` 唯一，`jobs.job_id` 唯一等）。
   - 实现 `/api/login`, `/api/upload`, `/api/submissions/<id>`, `/api/jobs/<id>` stub：写入 Mongo，返回 mock 状态。
   - 通过 `tests/integration/test_client_compat.py` 运行旧客户端，确保协议兼容。
2. **M2：队列 + CLI**（与之前一致，但状态持久化在 Mongo）。
3. **M3：React UI 原型**（最小界面即可）。
4. **M4：硬化 & 文档**（包含 `.env.example` 中的 `MONGODB_URI`、索引创建脚本、备份策略）。

## 尚需确认/待办
- `test_installation.py` 只作为遗留参考文件，后续是否完全移除需确认。
- 为 `astrometry_indexes/` 制定校验/更新策略（目前由本地快照提供，后续需说明如何同步 data.astrometry.net 的增量）。
- Annotated image 的下载 API 需要明确文件格式 & 命名策略，保证与旧客户端/前端兼容。

## 新人交付指南
1. 准备 Mongo 实例：
   - **测试环境**：运行 `scripts/start_mongodb.sh` 启动本地临时实例
   - **生产环境**：使用 Docker 或 MongoDB Atlas
   - 在 `.env` 中设置 `MONGODB_URI=mongodb://localhost:27017` 和 `MONGODB_DBNAME=<数据库名>`
2. 参照 README 安装 brew CLI，复用仓库根目录 `astrometry_indexes/` 中已缓存的 index files 并在 `.env` 中配置 `ASTROMETRY_INDEX_DIR`。
3. 按里程碑执行，阶段性运行 `tests/integration/test_client_compat.py` 以旧客户端为验收。
4. 更新本文件记录新增约束/配置信息。
