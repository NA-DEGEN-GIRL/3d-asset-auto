import asyncio
import json
import sys

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_handshake_and_tools(tmp_path):
    (tmp_path / "reference.png").write_bytes(b"local-planning-reference")

    async def run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "asset_auto.cli", "--root", str(tmp_path), "mcp"]
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert {
                "generate_asset", "edit_asset", "asset_job_status", "tripo_plan", "tripo_balance", "resume_tripo_asset"
            } <= {t.name for t in listing.tools}
            result = await session.call_tool("asset_capabilities", {})
            assert not result.isError
            invalid = await session.call_tool("generate_asset", {"spec": {"asset_id": "../escape"}})
            assert invalid.isError
            planned = await session.call_tool("tripo_plan", {"spec": {
                "asset_id": "cloud-prop", "provider": "tripo", "image": "reference.png",
            }})
            assert not planned.isError
            plan = json.loads(planned.content[0].text)
            assert plan["estimated_credits"] == 30 and plan["max_credits"] == 100 and plan["within_budget"]
            assert not (tmp_path / ".assets").exists()

    asyncio.run(run())
