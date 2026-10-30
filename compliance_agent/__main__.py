"""Run the compliance agent A2A server: python -m compliance_agent"""

import uvicorn

from common import config
from compliance_agent.agent import a2a_app

if __name__ == "__main__":
    uvicorn.run(a2a_app, host=config.BIND_HOST, port=config.COMPLIANCE_AGENT_PORT)
