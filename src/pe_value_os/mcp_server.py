from mcp.server import MCPServer
from pydantic import BaseModel

mcp = MCPServer("PE Portfolio Value Creation Operating System")


class Health(BaseModel):
    status: str
    version: str


@mcp.tool()
def healthcheck() -> Health:
    """Return service health."""
    return Health(status="ok", version="0.1.0")


@mcp.resource("project://policies")
def policies() -> str:
    return (
        "No autonomous management actions | No LLM-authored financial arithmetic | "
        "No cross-portco data leakage | No uncited value claim"
    )


app = mcp.streamable_http_app()
