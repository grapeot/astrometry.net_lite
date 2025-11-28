#!/bin/bash
# 在 Docker 容器内运行 MongoDB Admin TUI
# 用于访问 Docker 网络内的 MongoDB 实例

set -e

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 检查 Docker 是否运行
if ! docker info >/dev/null 2>&1; then
    echo "错误: Docker 未运行，请先启动 Docker"
    exit 1
fi

# 优先检查生产环境容器，再检查开发环境容器
BACKEND_CONTAINER=""
PROD_CONTAINER="astrometry-backend-prod"
DEV_CONTAINER="astrometry-backend"

# 检查生产环境容器是否运行
if docker ps --format '{{.Names}}' | grep -q "^${PROD_CONTAINER}$"; then
    BACKEND_CONTAINER="${PROD_CONTAINER}"
    echo "使用生产环境容器: ${BACKEND_CONTAINER}"
# 检查生产环境容器是否存在（但未运行）
elif docker ps -a --format '{{.Names}}' | grep -q "^${PROD_CONTAINER}$"; then
    echo "错误: 生产环境容器 ${PROD_CONTAINER} 存在但未运行"
    echo "请先启动服务: docker-compose -f docker-compose.prod.yml up -d"
    exit 1
# 检查开发环境容器是否运行
elif docker ps --format '{{.Names}}' | grep -q "^${DEV_CONTAINER}$"; then
    BACKEND_CONTAINER="${DEV_CONTAINER}"
    echo "使用开发环境容器: ${BACKEND_CONTAINER}"
# 检查开发环境容器是否存在（但未运行）
elif docker ps -a --format '{{.Names}}' | grep -q "^${DEV_CONTAINER}$"; then
    echo "错误: 开发环境容器 ${DEV_CONTAINER} 存在但未运行"
    echo "请先启动服务: docker-compose up -d"
    exit 1
else
    echo "错误: 找不到运行中的容器"
    echo "请先启动服务:"
    echo "  - 生产环境: docker-compose -f docker-compose.prod.yml up -d"
    echo "  - 开发环境: docker-compose up -d"
    exit 1
fi

echo "=========================================="
echo "在 Docker 容器内运行 MongoDB Admin TUI"
echo "容器: ${BACKEND_CONTAINER}"
echo "MongoDB: mongodb:27017 (Docker 网络内)"
echo ""
echo "提示: 按 Ctrl+C 退出 TUI"
echo "=========================================="
echo ""

# 在容器内运行 TUI
# 设置环境变量，让 TUI 连接到 Docker 网络内的 MongoDB
docker exec -it "${BACKEND_CONTAINER}" \
    env MONGODB_URI="mongodb://mongodb:27017" \
    python scripts/mongodb_admin_tui.py

