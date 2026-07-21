# Built from the repo root (compose sets context: .) so the SDK — whose
# plugins this service proxies through — installs from source.
FROM python:3.11-slim
WORKDIR /app
COPY sdk/python /sdk
RUN pip install --no-cache-dir /sdk
COPY platform/workbench/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY platform/workbench/app ./app
COPY platform/workbench/static ./static
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
