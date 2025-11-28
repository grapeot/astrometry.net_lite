# 端口配置指南

## 统一端口配置

所有服务的端口都可以通过环境变量统一配置。

**⚠️ 重要：Docker容器间通信 vs 外部端口映射**

在Docker Compose中：
- **容器内部端口**：MongoDB容器内部始终监听27017端口
- **主机端口映射**：`MONGODB_PORT`控制从宿主机访问MongoDB的端口
- **容器间通信**：后端和worker通过服务名`mongodb`连接，使用容器内部端口27017（不受`MONGODB_PORT`影响）

**示例**：
- 设置 `MONGODB_PORT=27018` 后：
  - 从宿主机访问：`mongodb://localhost:27018` ✅
  - 容器间通信：`mongodb://mongodb:27017` ✅（后端和worker自动使用这个）

## 配置方式

### 方式1: 使用 .env 文件（推荐）

在项目根目录创建 `.env` 文件：

```bash
# MongoDB端口
MONGODB_PORT=27017

# Backend API端口
API_PORT=8002

# Frontend端口
FRONTEND_PORT=5173

# MongoDB连接URI (可选，如果设置了MONGODB_PORT会自动更新端口)
MONGODB_URI=mongodb://localhost:27017

# API Host
API_HOST=127.0.0.1
```

### 方式2: 使用环境变量

在启动前设置环境变量：

```bash
export MONGODB_PORT=27017
export API_PORT=8002
export FRONTEND_PORT=5173
docker-compose up -d
```

### 方式3: 在docker-compose.yml中直接修改

编辑 `docker-compose.yml`，修改以下位置：

1. **MongoDB端口** (第12行):
   ```yaml
   ports:
     - "${MONGODB_PORT:-27017}:27017"
   ```

2. **Backend端口** (第28行和第50行):
   ```yaml
   ports:
     - "${API_PORT:-8002}:8002"
   ```
   和
   ```yaml
   command: sh -c "uvicorn api.main:app --host 0.0.0.0 --port $${API_PORT:-8002} --reload"
   ```

3. **Frontend端口** (第59行):
   ```yaml
   ports:
     - "${FRONTEND_PORT:-5173}:5173"
   ```

## 配置文件位置

### Backend配置
- **文件**: `core/config.py`
- **环境变量**: `API_PORT`, `MONGODB_PORT`, `MONGODB_URI`

### Frontend配置
- **文件**: `frontend/vite.config.ts`
- **环境变量**: `FRONTEND_PORT` 或 `VITE_FRONTEND_PORT`

### Docker Compose配置
- **文件**: `docker-compose.yml`
- 使用环境变量: `${API_PORT:-8002}` (默认值8002)

## 默认端口

- **MongoDB**: 27017
- **Backend API**: 8002
- **Frontend**: 5173

## 修改示例

### 示例1: 修改所有端口

创建 `.env` 文件：
```bash
MONGODB_PORT=27018
API_PORT=8003
FRONTEND_PORT=5174
```

然后重启服务：
```bash
docker-compose down
docker-compose up -d
```

### 示例2: 只修改Backend端口

```bash
export API_PORT=9000
docker-compose up -d
```

Backend将在 `http://localhost:9000` 运行。

## 重要说明：Docker容器间通信 vs 外部端口映射

### Docker环境中的端口配置

在Docker Compose中，有两种端口概念：

1. **容器内部端口**：容器内服务监听的端口（MongoDB容器内始终是27017）
2. **主机端口映射**：从宿主机访问容器服务的端口（`MONGODB_PORT`控制这个）

**关键点**：
- **容器间通信**：后端和worker容器通过服务名 `mongodb` 连接，使用**容器内部端口27017**
- **外部访问**：从宿主机访问MongoDB使用**主机端口**（`MONGODB_PORT`环境变量）

**示例**：
```yaml
# docker-compose.yml
ports:
  - "${MONGODB_PORT:-27017}:27017"  # 主机端口:容器端口
```

如果设置 `MONGODB_PORT=27018`：
- 从宿主机访问：`mongodb://localhost:27018` ✅
- 容器间通信：`mongodb://mongodb:27017` ✅（不受影响）

### 本地开发（非Docker）

如果不在Docker中运行，需要直接设置MongoDB URI：

```bash
# 方式1: 使用环境变量
export MONGODB_URI=mongodb://localhost:27018

# 方式2: 在.env文件中
MONGODB_URI=mongodb://localhost:27018
```

## 注意事项

1. **端口冲突**: 确保新端口没有被其他服务占用
2. **CORS设置**: 如果修改了Frontend端口，可能需要更新Backend的CORS配置
3. **环境变量优先级**: Docker Compose中的环境变量会覆盖`.env`文件
4. **重启服务**: 修改端口后需要重启所有相关服务
5. **Docker容器通信**: 容器间通信使用服务名和容器内部端口，不受`MONGODB_PORT`影响

## 验证配置

启动后检查端口：

```bash
# 检查MongoDB
docker-compose exec mongodb mongosh --eval "db.version()"

# 检查Backend
curl http://localhost:${API_PORT:-8002}/docs

# 检查Frontend
curl http://localhost:${FRONTEND_PORT:-5173}
```

