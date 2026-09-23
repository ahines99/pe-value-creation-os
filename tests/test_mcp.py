import pytest
from mcp import Client

from pe_value_os.mcp_server import mcp

pytestmark = pytest.mark.anyio


async def test_healthcheck():
    async with Client(mcp) as client:
        result = await client.call_tool("healthcheck", {})
        assert result.is_error is False
        assert result.structured_content == {"status": "ok", "version": "0.1.0"}
