#!/bin/bash
# filepath: start.sh

# 启动虚拟显示
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# 安装 Python 依赖
# pip3 install fastmcp aiohttp requests pillow

# 设置环境变量
export PYTHONPATH="/app/src:$PYTHONPATH"

# 启动 Blender（不会立即退出）
# blender --background --python /app/startup.py
blender --python /app/startup.py