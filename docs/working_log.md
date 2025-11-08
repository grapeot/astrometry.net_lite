# Astrometry.net Lite Working Log

_Updated: 2025-11-07_

## Purpose
跟踪 FastAPI + MongoDB 重构的实现进度：每个阶段、API 端点、测试/文档状态，以及需要额外信息或风险的事项。完成后会在此文档中打勾，便于你实时查看还缺什么。

## Milestone Checklist
- [x] M1：后端骨架（FastAPI、Pydantic Settings、Mongo 依赖注入）
- [x] M2：Mongo 队列 + CLI Worker（含 annotated image 生成）
- [ ] M3：兼容 API（登录/上传/查询/下载）
- [x] M4：前端最小界面（登录、上传、Job 列表/详情）
- [ ] M5：测试与文档（集成 + 单元 + README + Dockerfile）

## API Coverage Matrix
| Endpoint / Feature | Required by client | Status | Notes |
| --- | --- | --- | --- |
| `POST /api/login` | ✅ | ☐ | Session = API key for兼容 |
| `POST /api/login` | ✅ | ☑ | Session = API key for兼容 |
| `POST /api/upload` | ✅ | ☑ | 支持 file + request-json；写 submissions/jobs/queue |
| `POST /api/url_upload` | ✅ | ☑ | 远程 URL 下载落地后入队 |
| `GET/POST /api/submissions/{id}` | ✅ | ☑ | 返回 status/jobs 列表 |
| `GET/POST /api/submissions/{id}/jobs` | ✅ | ☑ | 兼容旧 JSON |
| `POST /api/submission_images` | ✅ | ☑ | 回传 image_ids |
| `GET/POST /api/jobs/{id}` | ✅ | ☑ | status + metadata |
| `GET/POST /api/jobs/{id}/calibration` | ✅ | ☐ | CLI 尚未写入 calibration (TODO) |
| `GET/POST /api/jobs/{id}/tags` | ✅ | ☑ | 初期返回空 |
| `GET/POST /api/jobs/{id}/machine_tags` | ✅ | ☑ | ditto |
| `GET/POST /api/jobs/{id}/objects_in_field` | ✅ | ☑ | 为空待 CLI 输出 |
| `GET/POST /api/jobs/{id}/annotations` | ✅ | ☑ | JSON 描述 |
| `GET/POST /api/jobs/{id}/info` | ✅ | ☑ | 包含基础 metadata |
| `GET/POST /api/myjobs/` | ✅ | ☑ | session=API key |
| `GET/POST /api/jobs_by_tag` | ✅ | ☑ | 简单标签搜索 |
| `/api/sdss_image_for_wcs` | ✅ | ☐ | TODO: 501 not implemented |
| `/api/galex_image_for_wcs` | ✅ | ☐ | TODO |
| `/wcs_file/{jobid}` | ✅ | ☑ | 读 artifacts |
| `/kml_file/{jobid}/` | ✅ | ☑ | 由 CLI `--kmz` 输出 |
| `/new_fits_file/{jobid}/` | ✅ | ☑ | 读 artifacts |
| `/corr_file/{jobid}` | ✅ | ☑ | 读 artifacts |
| `/annotated_display/{jobid}` | ✅ | ☑ | 目前为占位 PNG |

## Open Questions / Blocking Info
1. Annotated image 需确定最终格式（PNG? JPEG?）与 CLI 命令；若需自定义脚本请提供示例。（目前路由存在但暂不生成文件）
2. 如果需要 `jobs_by_tag` 真正查 tag，是否保留 Mongo `tags` 集合或实时扫描 `jobs`？默认准备稀疏字段。
3. Docker 化要求：基础镜像首选 `python:3.12-slim` 吗？是否需要包含 Homebrew CLI？
4. KMZ/KML 默认关闭（缺少 `wcs2kml`）；后续若要启用需明确安装路径和部署策略。

## Recent Notes
- 2025-11-07：完成 `.env` 初始化、确认 CLI 路径、更新 dev_plan、建立此 working log。
- 2025-11-07：实现 FastAPI 骨架 + Mongo 队列 + worker + React 控制台。遗留：calibration 数据解析、SDSS/GALEX overlay、jobs_by_tag 更细粒度过滤。
- 2025-11-08：本地 `solve-field` 已在 `test.jpg` 上跑通（示例命令见 dev_plan），确认输出文件集及日志可用于填充 calibration/annotations。
