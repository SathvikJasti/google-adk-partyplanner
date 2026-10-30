"""Service addresses and ports, shared by every service.

Each value can be overridden with an env var (or in .env), so the same code
runs locally, in containers, or behind a load balancer without changes.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

# Explicit env vars win over .env, as in production deployments.
load_dotenv(ROOT / ".env", override=False)

# Interface the servers listen on, and the hostname other services use to reach
# them. 127.0.0.1 rather than "localhost": on Windows, localhost tries IPv6 (::1)
# first, which the servers don't listen on, adding a stall to every call.
BIND_HOST = os.getenv("BIND_HOST", "127.0.0.1")
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "127.0.0.1")

PARTY_PLANNER_PORT = int(os.getenv("PARTY_PLANNER_PORT", "8000"))
BUDGET_AGENT_PORT = int(os.getenv("BUDGET_AGENT_PORT", "8001"))
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8002"))
COMPLIANCE_AGENT_PORT = int(os.getenv("COMPLIANCE_AGENT_PORT", "8003"))

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", f"http://{PUBLIC_HOST}:{MCP_SERVER_PORT}/mcp")
BUDGET_AGENT_URL = os.getenv("BUDGET_AGENT_URL", f"http://{PUBLIC_HOST}:{BUDGET_AGENT_PORT}")
COMPLIANCE_AGENT_URL = os.getenv("COMPLIANCE_AGENT_URL", f"http://{PUBLIC_HOST}:{COMPLIANCE_AGENT_PORT}")

# Seconds to wait on a remote agent (A2A) or the MCP server before giving up.
A2A_TIMEOUT = float(os.getenv("A2A_TIMEOUT", "120"))
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT", "10"))
