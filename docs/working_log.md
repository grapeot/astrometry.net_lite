# Astrometry.net Lite Working Log

_Updated: 2025-11-07_

## Purpose
跟踪 FastAPI + MongoDB 重构的实现进度：每个阶段、API 端点、测试/文档状态，以及需要额外信息或风险的事项。完成后会在此文档中打勾，便于你实时查看还缺什么。

## Milestone Checklist
- [ ] M1：后端骨架（FastAPI、Pydantic Settings、Mongo 依赖注入）
- [ ] M2：Mongo 队列 + CLI Worker（含 annotated image 生成）
- [ ] M3：兼容 API（登录/上传/查询/下载）
- [ ] M4：前端最小界面（登录、上传、Job 列表/详情）
- [ ] M5：测试与文档（集成 + 单元 + README + Dockerfile）

## API Coverage Matrix
| Endpoint / Feature | Required by client | Status | Notes |
| --- | --- | --- | --- |
| `POST /api/login` | ✅ | ☐ | Session = API key for兼容 |
| `POST /api/upload` | ✅ | ☐ | 支持 file + request-json；写 submissions/jobs/queue |
| `POST /api/url_upload` | ✅ | ☐ | 远程 URL 下载落地后入队 |
| `GET /api/submissions/{id}` | ✅ | ☐ | 返回 status/jobs 列表 |
| `GET /api/submissions/{id}/jobs` | ✅ | ☐ | 兼容旧 JSON |
| `GET /api/submission_images` | ✅ | ☐ | 回传 image_ids |
| `GET /api/jobs/{id}` | ✅ | ☐ | status + metadata |
| `GET /api/jobs/{id}/calibration` | ✅ | ☐ | 来自 CLI 结果 |
| `GET /api/jobs/{id}/tags` | ✅ | ☐ | 初期可返回空列表 |
| `GET /api/jobs/{id}/machine_tags` | ✅ | ☐ | ditto |
| `GET /api/jobs/{id}/objects_in_field` | ✅ | ☐ | 解析 CLI 输出 |
| `GET /api/jobs/{id}/annotations` | ✅ | ☐ | JSON 描述 & annotate_data |
| `GET /api/jobs/{id}/info` | ✅ | ☐ | 包含 created/start/end |
| `GET /api/myjobs/` | ✅ | ☐ | 过滤当前 session jobs |
| `GET /api/jobs_by_tag` | ✅ | ☐ | 支持 ?query= & exact |
| `/api/sdss_image_for_wcs` | ✅ | ☐ | overlay_plot 输入 WCS |
| `/api/galex_image_for_wcs` | ✅ | ☐ | 同上 |
| `/wcs_file/{jobid}` | ✅ | ☐ | 下载 fits |
| `/kml_file/{jobid}/` | ✅ | ☐ | 下载 kmz |
| `/new_fits_file/{jobid}/` | ✅ | ☐ | 下载 new fits |
| `/corr_file/{jobid}` | ✅ | ☐ | 下载 corr fits |
| `/annotated_display/{jobid}` | ✅ | ☐ | PNG/JPEG annotated image |

## Open Questions / Blocking Info
1. Annotated image 需确定最终格式（PNG? JPEG?）与 CLI 命令；若需自定义脚本请提供示例。
2. 如果需要 `jobs_by_tag` 真正查 tag，是否保留 Mongo `tags` 集合或实时扫描 `jobs`？默认准备稀疏字段。
3. Docker 化要求：基础镜像首选 `python:3.12-slim` 吗？是否需要包含 Homebrew CLI？

## Recent Notes
- 2025-11-07：完成 `.env` 初始化、确认 CLI 路径、更新 dev_plan、建立此 working log。

