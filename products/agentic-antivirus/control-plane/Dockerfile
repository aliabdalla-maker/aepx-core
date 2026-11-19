# Build context: products/agentic-antivirus (needs detection/, monetization/, shared/). Multi-arch (amd64, arm64).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/detection
WORKDIR /app/control-plane
COPY control-plane/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 aav
COPY detection /app/detection
COPY monetization /app/monetization
COPY shared /app/shared
COPY control-plane/app ./app
COPY control-plane/migrations ./migrations
RUN mkdir -p /var/lib/aav/files && chown aav /var/lib/aav/files
USER aav
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
