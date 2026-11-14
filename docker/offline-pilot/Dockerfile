# Offline pilot image: build in an explicitly controlled environment.
# Runtime must be started only via scripts/run_aepx_offline_docker.sh.
FROM python:3.12-slim
RUN groupadd --gid 10001 pilot && useradd --uid 10001 --gid 10001 --no-create-home pilot
WORKDIR /workspace
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python","-I","/workspace/scripts/aepx_supervised_batch.py"]
