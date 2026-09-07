"""Optional MCP stdio transport; no model/provider initialization or approval tools."""
import argparse
import asyncio
import json
from pathlib import Path


def make_server(service,permissions):
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    from loop_robot.terminal.simulation import TOOLS,call_service
    server=Server('loop-simulation')

    @server.list_tools()
    async def list_tools():
        return [Tool(name=t['function']['name'],description=t['function']['description'],inputSchema=t['function']['parameters']) for t in TOOLS]

    @server.call_tool()
    async def call_tool(name,arguments):
        # Keep rendering on the owning thread; no threadpool scene mutations.
        snapshot=permissions.snapshot()
        if snapshot['mode'] != 'plan' and snapshot['rules'].get(name) == 'ask':
            raise PermissionError('MCP has no approval UI. The operator must review this action and set its rule in Loop using the same state directory; no tool can self-approve: '+name)
        result=call_service(service,permissions,name,arguments)
        return [TextContent(type='text',text=json.dumps(result,ensure_ascii=False,allow_nan=False))]
    return server


def main(argv=None):
    from loop_robot.terminal.config import DEFAULT_STATE_DIR
    from loop_robot.terminal.home import loop_home
    parser=argparse.ArgumentParser(description='Loop robotics simulation MCP server (stdio)')
    parser.add_argument('--state-dir',type=Path,default=DEFAULT_STATE_DIR)
    parser.add_argument('--isaac-config',type=Path,default=loop_home()/'isaac-bridge.json')
    args=parser.parse_args(argv)
    try:
        from mcp.server.stdio import stdio_server
    except ImportError as exc:
        raise RuntimeError('Install Loop optional dependencies: pip install "loop-ros[mcp,sim,dataset]"') from exc
    from loop_robot.terminal.permissions import PermissionGate
    from loop_robot.toolchain.simulation import SimulationWorkbench
    args.state_dir.mkdir(parents=True,exist_ok=True)
    gate=PermissionGate(args.state_dir/'permissions.sqlite')
    service=SimulationWorkbench(args.state_dir/'simulation',args.isaac_config)
    server=make_server(service,gate)
    async def run():
        async with stdio_server() as (read,write):
            await server.run(read,write,server.create_initialization_options())
    try: asyncio.run(run())
    finally: service.close()


if __name__=='__main__': main()
