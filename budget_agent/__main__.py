"""Run the budget agent A2A server: python -m budget_agent"""

import uvicorn

from budget_agent.agent import a2a_app
from common import config

if __name__ == "__main__":
    uvicorn.run(a2a_app, host=config.BIND_HOST, port=config.BUDGET_AGENT_PORT)
