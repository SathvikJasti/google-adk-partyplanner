from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def health_route(service_name: str) -> Route:
    """GET /health liveness probe, used by the start script and load balancers."""

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": service_name})

    return Route("/health", health, methods=["GET"])
