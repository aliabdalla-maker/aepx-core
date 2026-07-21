# Built from the repo root (compose sets context: .) so the SDK — which
# carries the conformance engine this service runs — installs from source.
FROM python:3.11-slim
WORKDIR /app
COPY sdk/python /sdk
RUN pip install --no-cache-dir /sdk
COPY platform/conformance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY platform/conformance/app ./app
COPY platform/conformance/static ./static
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
