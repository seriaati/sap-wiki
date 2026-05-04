import os

from .server import mcp

if __name__ == "__main__":
    mcp.settings.host = os.getenv("HOST", "0.0.0.0")
    mcp.settings.port = int(os.getenv("PORT", "8765"))
    mcp.run(transport="streamable-http")
