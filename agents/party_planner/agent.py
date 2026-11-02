from pathlib import Path

import yaml
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

from common import auth, config

CFG = yaml.safe_load((Path(__file__).parent / "instructions.yaml").read_text(encoding="utf-8"))

# MCP: data server over Streamable HTTP (port 8002)
mcp_tools = McpToolset(
    header_provider=auth.mcp_headers if config.SERVICE_AUTH else None,
    connection_params=StreamableHTTPConnectionParams(
        url=config.MCP_SERVER_URL,
        timeout=config.MCP_TIMEOUT,
    ),
)

# A2A clients for the two specialist agents, each running as its own server
remote_budget_agent = RemoteA2aAgent(
    name="budget_agent",
    description=CFG["remote_agent_descriptions"]["budget_agent"].strip(),
    agent_card=config.BUDGET_AGENT_URL + AGENT_CARD_WELL_KNOWN_PATH,
    timeout=config.A2A_TIMEOUT,
    httpx_client=auth.a2a_http_client(),
)
remote_compliance_agent = RemoteA2aAgent(
    name="compliance_agent",
    description=CFG["remote_agent_descriptions"]["compliance_agent"].strip(),
    agent_card=config.COMPLIANCE_AGENT_URL + AGENT_CARD_WELL_KNOWN_PATH,
    timeout=config.A2A_TIMEOUT,
    httpx_client=auth.a2a_http_client(),
)

root_agent = Agent(
    name="party_planner",
    model=CFG["model"],
    description=CFG["party_planner"]["description"].strip(),
    instruction=CFG["party_planner"]["instruction"],
    tools=[
        mcp_tools,
        # Delegate-and-return: each specialist is called like a tool.
        # The result comes back to party_planner, which writes the final answer.
        AgentTool(agent=remote_budget_agent),
        AgentTool(agent=remote_compliance_agent),
    ],
)
