# render_scene.py
import bpy

# 添加一个立方体
bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))

# 保存文件
bpy.ops.wm.save_as_mainfile(filepath="output.blend")

print("脚本执行完成！")

while True:
    # 保持脚本运行状态
    pass