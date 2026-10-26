"""Local Reticle MCP bridge; uses the SDK version installed in this app."""
import asyncio
import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    commands = json.loads(sys.argv[1])
    expected_url = sys.argv[2] if len(sys.argv) > 2 else None
    params = StdioServerParameters(command="npx.cmd", args=["--yes", "--package=@reticlehq/server@3.7.0", "--package=@reticlehq/core@3.7.0", "reticle", "mcp"], cwd=r"D:\voice agent")
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            # The CLI-owned daemon can start after the page's first connection.
            # Wait for the SDK's normal reconnect before driving that page.
            session_id = None
            for attempt in range(15):
                listing = await session.call_tool("reticle_session", {"action": "list"})
                payload = " ".join(item.text for item in listing.content if hasattr(item, "text"))
                def find_session(value):
                    if isinstance(value, dict):
                        if value.get("url") == expected_url:
                            return value.get("sessionId") or value.get("id")
                        return next((found for item in value.values() if (found := find_session(item))), None)
                    if isinstance(value, list):
                        return next((found for item in value if (found := find_session(item))), None)
                    return None
                if expected_url:
                    session_id = find_session(json.loads(payload))
                if session_id or not expected_url:
                    break
                await asyncio.sleep(1)
            for command in commands:
                args = dict(command.get("args", {}))
                if session_id:
                    args["sessionId"] = session_id
                result = await session.call_tool(command["tool"], args)
                print(json.dumps({"tool": command["tool"], "result": result.model_dump(mode="json")}, ensure_ascii=True))


asyncio.run(main())
