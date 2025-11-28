#!/bin/bash
# 临时 MongoDB 启动脚本
# 用于在项目目录下启动一个独立的 MongoDB 实例用于测试

set -e

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 配置（相对于项目根目录）
DATA_DIR="$PROJECT_ROOT/data/mongodb"
LOG_FILE="$PROJECT_ROOT/data/mongodb.log"
PORT=27017
MONGOD_BIN="/opt/homebrew/bin/mongod"

# 检查 mongod 是否存在
if [ ! -f "$MONGOD_BIN" ]; then
    echo "错误: 找不到 mongod，请确保已安装 MongoDB"
    exit 1
fi

# 创建数据目录
if [ ! -d "$DATA_DIR" ]; then
    echo "创建数据目录: $DATA_DIR"
    mkdir -p "$DATA_DIR"
fi

# 检查端口是否被占用
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "警告: 端口 $PORT 已被占用"
    echo "如果这是另一个 MongoDB 实例，请先停止它"
    echo "或者修改脚本中的 PORT 变量使用其他端口"
    exit 1
fi

echo "=========================================="
echo "启动临时 MongoDB 实例"
echo "数据目录: $DATA_DIR"
echo "端口: $PORT"
echo "日志文件: $LOG_FILE"
echo ""
echo "连接字符串: mongodb://localhost:$PORT"
echo ""
echo "按 Ctrl+C 停止 MongoDB"
echo "=========================================="
echo ""

# 启动 MongoDB（前台运行）
exec "$MONGOD_BIN" \
    --dbpath "$DATA_DIR" \
    --port "$PORT" \
    --logpath "$LOG_FILE" \
    --logappend \
    --bind_ip 127.0.0.1


