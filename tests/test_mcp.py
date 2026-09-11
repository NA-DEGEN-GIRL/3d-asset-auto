import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_handshake_and_tools():
    async def run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "asset_auto.cli", "--root", str(Path.cwd()), "mcp"]
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert {"generate_asset", "edit_asset", "asset_job_status"} <= {t.name for t in listing.tools}
            result = await session.call_tool("asset_capabilities", {})
            assert not result.isError
            invalid = await session.call_tool("generate_asset", {"spec": {"asset_id": "../escape"}})
            assert invalid.isError

    asyncio.run(run())
