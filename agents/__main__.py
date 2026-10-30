"""Serve the party planner through Google ADK (web UI + REST/SSE API): python -m agents

Same server as `adk web agents`, but OTel is configured around ADK's own setup
and the FastAPI app is instrumented, so the orchestrator shows up in Grafana.
"""

from pathlib import Path

from common import config  # loads .env, including the OTEL_* exporter settings
from common.telemetry import bridge_python_logging, instrument_app, setup_telemetry

SERVICE_NAME = "party_planner"

# Metrics provider + instrumentation now; ADK adds the tracer/logger providers below.
setup_telemetry(SERVICE_NAME, adk_web_server=True)

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

# ADK creates the tracer and logger providers here, exporting over OTLP because
# OTEL_EXPORTER_OTLP_ENDPOINT is set. (It also logs that the meter provider
# can't be overridden; that's expected, ours is already in place.)
app = get_fast_api_app(
    agents_dir=str(Path(__file__).parent),
    web=True,
    host=config.PUBLIC_HOST,
    port=config.PARTY_PLANNER_PORT,
)
bridge_python_logging()
# Skip the probe and the web UI's static assets.
instrument_app(app, excluded_urls="list-apps,dev-ui")

if __name__ == "__main__":
    uvicorn.run(app, host=config.BIND_HOST, port=config.PARTY_PLANNER_PORT)
