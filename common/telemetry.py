"""Shared OpenTelemetry setup (traces, metrics, logs) for every service.

Exporters read the standard OTEL_* env vars (see .env), so pointing a service
at a different collector or a managed backend needs no code change.
"""

import logging
import os

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.starlette import _get_default_span_details
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from common import config  # noqa: F401  (loads .env before the exporters read it)


# The default HTTP duration buckets stop at 10s, but an agent request takes
# minutes, so every p95 would read "10s". Extend them for HTTP and A2A calls.
_DURATION_BUCKETS_S = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10,
                       20, 30, 45, 60, 90, 120, 180, 240, 300, 450, 600)
_VIEWS = [
    View(instrument_name=name, aggregation=ExplicitBucketHistogramAggregation(_DURATION_BUCKETS_S))
    for name in ("http.server.request.duration", "http.client.request.duration")
]


def setup_telemetry(service_name: str, *, adk_web_server: bool = False) -> None:
    """Call once per process, before any agent, MCP server or HTTP client is built.

    adk_web_server=True is for the party planner, and must be called before
    get_fast_api_app(): ADK then creates the tracer and logger providers itself
    from the same OTEL_* env vars (also feeding its dev UI's trace view), so we
    only create the meter provider (ADK's has no bucket views) and call
    bridge_python_logging() once ADK is up.
    """
    os.environ["OTEL_SERVICE_NAME"] = service_name
    resource = Resource.create({"service.name": service_name})
    _create_meter_provider(resource)
    if not adk_web_server:
        _create_tracer_and_logger_providers(resource)
    _instrument_libraries()
    if not adk_web_server:
        bridge_python_logging()


def instrument_app(app, *, excluded_urls: str = "health") -> None:
    """Server span + http.server.* metrics per request, joined to the caller's
    trace via its traceparent header.

    Same middleware StarletteInstrumentor installs, but with options it doesn't
    expose: skip probe URLs, and drop the per-chunk "http send/receive" spans
    that SSE streams produce by the hundred.
    """
    app.add_middleware(
        OpenTelemetryMiddleware,
        excluded_urls=excluded_urls,
        default_span_details=_get_default_span_details,  # route-templated span names
        exclude_spans=["receive", "send"],
    )


def _create_meter_provider(resource: Resource) -> None:
    # Export interval comes from OTEL_METRIC_EXPORT_INTERVAL.
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader], views=_VIEWS))


def _create_tracer_and_logger_providers(resource: Resource) -> None:
    if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
        return  # already configured in this process

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    _logs.set_logger_provider(logger_provider)


def _instrument_libraries() -> None:
    # Injects the W3C traceparent header into outgoing A2A and MCP calls, so the
    # receiving service's spans join the caller's trace.
    httpx = HTTPXClientInstrumentor()
    if not httpx.is_instrumented_by_opentelemetry:
        httpx.instrument()

    # LLM call spans and gen_ai.client.* metrics (latency, token usage).
    try:
        from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
    except ImportError:
        return
    genai = GoogleGenAiSdkInstrumentor()
    if not genai.is_instrumented_by_opentelemetry:
        genai.instrument()


def bridge_python_logging() -> None:
    """Send standard `logging` records to OTel (with trace/span ids) and the console."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if any(isinstance(h, LoggingHandler) for h in root.handlers):
        return
    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        root.addHandler(console)
    root.addHandler(LoggingHandler(level=logging.INFO, logger_provider=_logs.get_logger_provider()))
