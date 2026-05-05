import os

from .server import mcp

if __name__ == "__main__":
    mcp.settings.port = int(os.getenv("PORT", "8765"))
    mcp.run(transport="streamable-http")
