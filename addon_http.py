# This file should be installed in the Blender addons directory.

import base64
import bpy
from bpy.props import BoolProperty, IntProperty
import contextlib
import http.server
import io
import json
import os
import tempfile
import time
import threading
import uuid


bl_info = {
    'name': 'Blender HTTP',
    'author': 'BlenderHttp',
    'version': (1, 0),
    'blender': (3, 0, 0),
    'location': 'View3D > Sidebar > BlenderHttp',
    'description': 'Run Python code in Blender via HTTP',
    'category': 'Interface',
}


class BlenderHttpServer(http.server.BaseHTTPRequestHandler):

    @staticmethod
    def execute_code(code, globals=None, locals=None):
        exec_out = io.StringIO()
        try:
            with contextlib.redirect_stdout(exec_out):
                exec(code, globals, locals)
                return exec_out.getvalue()
        except Exception as e:
            return repr(e)

    @staticmethod
    def get_scene_info():
        return {
            'name': bpy.context.scene.name,
            'object_count': len(bpy.context.scene.objects),
            'materials_count': len(bpy.data.materials),
            'objects': [
                {
                    'name': obj.name,
                    'type': obj.type,
                    'location': '{:.3f}, {:.3f}, {:.3f}'.format(
                        obj.location.x, obj.location.y, obj.location.z),
                }
                for obj in bpy.context.scene.objects
            ],
        }

    @staticmethod
    def preview(filepath, rough_max_height=416):
        temp_dir = tempfile.gettempdir()
        filepath = os.path.join(
            temp_dir, 'blender_preview_{}.png'.format(str(uuid.uuid4())))

        # Find 3D viewport area
        viewport_area = None
        viewport_region = None
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                viewport_area = area
                for region in area.regions:
                    if region.type == 'WINDOW':
                        viewport_region = region
                        break

                break

        assert viewport_area and viewport_region, '3D viewport area not found'
        assert viewport_region.width > 0 and viewport_region.height > 0, 'Invalid viewport dimensions'

        # Ensure output directory exists
        output_dir = os.path.dirname(filepath)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Use context manager to temporarily modify render settings
        with render_settings_override(
            resolution_x=viewport_region.width,
            resolution_y=viewport_region.height,
            resolution_percentage=(
                int(round(100 * rough_max_height / viewport_region.height))
                if viewport_region.height > rough_max_height else 100
            ),
            filepath=filepath,
            **{
                'image_settings.file_format': 'PNG',
                'image_settings.color_mode': 'RGBA',
                'image_settings.color_depth': '8',
                'image_settings.compression': 15
            }
        ):
            with bpy.context.temp_override(area=viewport_area):
                bpy.ops.render.opengl(write_still=True)

        # load the temporary file as data uri then clean
        with open(filepath, 'rb') as f:
            data = f.read()
            base64_data = base64.b64encode(data).decode('utf-8')

        os.remove(filepath)
        return 'data:image/png;base64,{}'.format(base64_data)

    def do_GET(self):
        if self.path == '/scene_info':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            response = schedule_to_main_thread_then_wait(
                BlenderHttpServer.get_scene_info)
            self.wfile.write(
                json.dumps(response, ensure_ascii=False).encode('utf-8'))
        else:
            self.send_error(404, 'Not Found')

    def do_POST(self):
        if self.path == '/exec':
            post_data = self.rfile.read(
                int(self.headers.get('Content-Length', 0)))
            exec_out = schedule_to_main_thread_then_wait(
                BlenderHttpServer.execute_code, post_data.decode('utf-8'))
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(exec_out.encode('utf-8'))

        elif self.path == '/preview':
            post_data = self.rfile.read(
                int(self.headers.get('Content-Length', 0)))
            data = json.loads(post_data.decode('utf-8') or '{}')
            image_data_uri = schedule_to_main_thread_then_wait(
                BlenderHttpServer.preview,
                data.get('rough_max_height', 416))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(image_data_uri.encode('utf-8'))

        else:
            self.send_error(404, 'Not Found')


class ServerManager:
    def __init__(self, server):
        self.server = server
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.thread.join()


class BLENDERHTTP_PT_Panel(bpy.types.Panel):
    bl_label = 'Blender HTTP Server'
    bl_idname = 'BLENDERHTTP_PT_Panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BlenderHttp'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, 'blenderhttp_port')
        if not scene.blenderhttp_server_running:
            layout.operator('blenderhttp.start_server', text='Start server')
        else:
            layout.operator('blenderhttp.stop_server', text='Stop server')
            layout.label(text=f'Running on port {scene.blenderhttp_port}')


class BLENDERHTTP_OT_StartServer(bpy.types.Operator):
    bl_idname = 'blenderhttp.start_server'
    bl_label = 'Start the service'
    bl_description = 'Start the BlenderHttp server to execute Python code'

    def execute(self, context):
        scene = context.scene

        # Create a new server instance
        if not hasattr(bpy.types, 'blenderhttp_server') or not bpy.types.blenderhttp_server:
            server_address = ('localhost', scene.blenderhttp_port)
            bpy.types.blenderhttp_server = ServerManager(
                http.server.HTTPServer(server_address, BlenderHttpServer))

        # Start the server
        bpy.types.blenderhttp_server.start()
        scene.blenderhttp_server_running = True

        return {'FINISHED'}


class BLENDERHTTP_OT_StopServer(bpy.types.Operator):
    bl_idname = 'blenderhttp.stop_server'
    bl_label = 'Stop the service'
    bl_description = 'Stop the BlenderHttp server'

    def execute(self, context):
        scene = context.scene

        # Stop the server if it exists
        if hasattr(bpy.types, 'blenderhttp_server') and bpy.types.blenderhttp_server:
            bpy.types.blenderhttp_server.stop()
            del bpy.types.blenderhttp_server

        scene.blenderhttp_server_running = False

        return {'FINISHED'}


class Waitable:
    def __init__(self, func, *args):
        self.func = func
        self.args = args
        self.result = None
        self.done = False

    def __call__(self):
        self.result = self.func(*self.args)
        self.done = True

    def join(self):
        while not self.done:
            time.sleep(0.01)

        return self.result


@contextlib.contextmanager
def render_settings_override(**settings):
    """
    Context manager for temporarily modifying render settings, automatically
    restores original settings on exit

    Args:
        **settings: Render settings to temporarily modify
    """
    scene = bpy.context.scene

    # Save original settings
    original_settings = {}

    for key, value in settings.items():
        if '.' in key:
            # Handle nested attributes like 'image_settings.file_format'
            obj_path, attr = key.rsplit('.', 1)
            obj = scene.render
            for part in obj_path.split('.'):
                obj = getattr(obj, part)
            original_settings[key] = getattr(obj, attr)
            setattr(obj, attr, value)
        else:
            # Handle direct attributes
            original_settings[key] = getattr(scene.render, key)
            setattr(scene.render, key, value)

    try:
        yield scene.render

    finally:
        # Restore original settings
        for key, original_value in original_settings.items():
            if '.' in key:
                obj_path, attr = key.rsplit('.', 1)
                obj = scene.render
                for part in obj_path.split('.'):
                    obj = getattr(obj, part)
                setattr(obj, attr, original_value)
            else:
                setattr(scene.render, key, original_value)


def register():
    bpy.types.Scene.blenderhttp_port = IntProperty(
        name='Port', description='Port for the BlenderHttp server',
        default=9876, min=1024, max=65535)
    bpy.types.Scene.blenderhttp_server_running = BoolProperty(
        name='Server Running', default=False)

    bpy.utils.register_class(BLENDERHTTP_PT_Panel)
    bpy.utils.register_class(BLENDERHTTP_OT_StartServer)
    bpy.utils.register_class(BLENDERHTTP_OT_StopServer)


def unregister():
    # Stop the server if it's running
    if hasattr(bpy.types, 'blenderhttp_server') and bpy.types.blenderhttp_server:
        bpy.types.blenderhttp_server.stop()
        del bpy.types.blenderhttp_server

    bpy.utils.unregister_class(BLENDERHTTP_PT_Panel)
    bpy.utils.unregister_class(BLENDERHTTP_OT_StartServer)
    bpy.utils.unregister_class(BLENDERHTTP_OT_StopServer)

    del bpy.types.Scene.blenderhttp_port
    del bpy.types.Scene.blenderhttp_server_running


def schedule_to_main_thread_then_wait(func, *args):
    waitable = Waitable(func, *args)
    bpy.app.timers.register(waitable, first_interval=0.0)
    return waitable.join()


if __name__ == '__main__':
    register()