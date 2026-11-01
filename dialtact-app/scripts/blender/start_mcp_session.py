"""
Open Blender ready for the Blender MCP bridge, with the Dialtact mascot loaded.

  blender --python scripts/blender/start_mcp_session.py -- [model.glb]

Enables the "MCP for Blender" add-on, starts its socket server (localhost:9876, the
port the `blender-mcp` MCP server connects to) and imports the mascot so it is the
scene Claude works on. Needs the Blender UI: the add-on's server runs on UI timers.
"""
import sys

import addon_utils
import bpy

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
model = args[0] if args else None

addon_utils.enable('blender_mcp', default_set=True, persistent=True)


def start():
    if bpy.context.scene is None:
        return 0.5
    if model:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()
        bpy.ops.import_scene.gltf(filepath=model)
        print(f'BlenderMCP session: imported {model}')
    server = getattr(bpy.types, 'blendermcp_server', None)
    if server is None or not server.running:
        bpy.ops.blendermcp.start_server()
    server = getattr(bpy.types, 'blendermcp_server', None)
    print('BlenderMCP session: server running =', bool(server and server.running), 'port', bpy.context.scene.blendermcp_port)
    return None


bpy.app.timers.register(start, first_interval=1.0)
