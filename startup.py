import bpy
import sys
import threading
import time
import subprocess
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
sys.path.append('/app')
sys.path.append('/app/src')

logger.info("Blender addon server started")

# 在单独进程中启动 MCP 服务器
def start_mcp_process():
    time.sleep(3)
    logger.info("Starting MCP server process...")
    env = os.environ.copy()
    # 不捕获输出，让它直接输出到终端
    # process = subprocess.Popen([
    #     'blender', '--background', '--python', 'addon_http.py'
    # ], cwd='/app', env=env)
    process = subprocess.Popen([
        "blender", "--background", "--addons", "BlenderHTTP", "--python", "/app/addon_http.py"
    ])
    logger.info(f"MCP server process started with PID: {process.pid}")
    # 等待进程结束
    return_code = process.wait()
    logger.error(f"MCP server exited with code: {return_code}")

threading.Thread(target=start_mcp_process, daemon=False).start()  # daemon=False

logger.info("Services started, keeping alive...")
while True:
    time.sleep(1)