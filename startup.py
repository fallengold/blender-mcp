import bpy
import sys
import threading
import time
import subprocess
import os
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 添加路径
sys.path.append('/app')
sys.path.append('/app/src')

# 注册插件
import addon
addon.register()

# 启动 Blender 服务器
bpy.context.scene.blendermcp_port = 9876
bpy.ops.blendermcp.start_server()

logger.info("Blender addon server started")

# 在单独进程中启动 MCP 服务器
def start_mcp_process():
    time.sleep(3)
    
    logger.info("Starting MCP server process...")
    
    # 设置环境变量
    env = os.environ.copy()
    env['PYTHONPATH'] = '/app/src'
    
    # 不捕获输出，让它直接输出到终端
    process = subprocess.Popen([
        '/usr/bin/python3', '-m', 'blender_mcp.server'
    ], cwd='/app', env=env)
    
    logger.info(f"MCP server process started with PID: {process.pid}")
    
    # 等待进程结束
    return_code = process.wait()
    logger.error(f"MCP server exited with code: {return_code}")

threading.Thread(target=start_mcp_process, daemon=False).start()  # daemon=False

logger.info("Services started, keeping alive...")
while True:
    time.sleep(1)