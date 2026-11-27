"""OpenTelemetry traces (BE-06). Enabled only when OTEL_EXPORTER_OTLP_ENDPOINT is set (standard OTel variable);
otherwise nothing is imported or exported. Every HTTP request becomes a server span; incoming W3C `traceparent`
headers are honoured, so agent and console requests join one trace. Health and readiness probes are excluded.

Deployment: deploy/compose.otel.yml runs a small OpenTelemetry Collector beside the stack (OTLP/HTTP on the
internal network, file export with rotation on the VM disk: Always Free, no external service). Point
OTEL_EXPORTER_OTLP_ENDPOINT at http://otel-collector:4318.
"""
from __future__ import annotations

import os

EXCLUDED = "health,ready,/api/health,/api/ready"


def setup(app, exporter=None) -> bool:
    if exporter is None and not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "agentic-antivirus-control-plane"),
        "service.version": app.version,
        "deployment.environment": os.getenv("AAV_ENVIRONMENT", "development"),
        "service.instance.id": os.getenv("AAV_BUILD_SHA", "unknown"),
    })
    provider = TracerProvider(resource=resource)
    if exporter is None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=EXCLUDED)
    if exporter is None:
        trace.set_tracer_provider(provider)
    return True
