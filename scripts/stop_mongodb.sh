#!/bin/bash
# 停止临时 MongoDB 实例

PORT=27017

# 查找运行在指定端口的 MongoDB 进程
PID=$(lsof -ti :$PORT 2>/dev/null || echo "")

if [ -z "$PID" ]; then
    echo "没有找到运行在端口 $PORT 的 MongoDB 进程"
    exit 0
fi

echo "找到 MongoDB 进程 (PID: $PID)"
echo "正在停止..."

kill "$PID"

# 等待进程结束
sleep 2

# 检查是否还在运行
if lsof -ti :$PORT >/dev/null 2>&1; then
    echo "强制停止..."
    kill -9 "$PID" 2>/dev/null || true
fi

echo "MongoDB 已停止"


