# 快速启动指南

## 一键启动（4 个终端窗口）

### 终端 1: MongoDB
```bash
./scripts/start_mongodb.sh
```

### 终端 2: 后端 API
```bash
./scripts/start_backend.sh
```

### 终端 3: Worker（处理队列）
```bash
./scripts/start_worker.sh
```

### 终端 4: 前端（可选）
```bash
./scripts/start_frontend.sh
```

## 首次启动前的准备

### 1. 初始化 API Key
```bash
PYTHONPATH=. python scripts/seed_api_key.py test-key-12345 test@example.com
```

### 2. 确认配置文件
确保 `.env` 文件存在并配置正确（参考 `core/config.py` 默认值）

## 测试服务

### 快速测试（不等待 Job 完成）
```bash
python scripts/test_service.py --quick
```

### 完整测试（等待 Job 完成）
```bash
python scripts/test_service.py --file test.jpg --apikey test-key-12345
```

## 访问地址

- **API**: http://127.0.0.1:8002
- **前端**: http://localhost:5173
- **API 文档**: http://127.0.0.1:8002/docs

## 详细文档

查看 `docs/START_GUIDE.md` 获取完整的启动说明和故障排除指南。

