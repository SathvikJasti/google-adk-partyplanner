"""Run the MCP data server: python -m mcp_server"""

import uvicorn

from common import config
from mcp_server.server import app

if __name__ == "__main__":
    uvicorn.run(app, host=config.BIND_HOST, port=config.MCP_SERVER_PORT)
