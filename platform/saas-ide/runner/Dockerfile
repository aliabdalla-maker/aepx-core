# AEP-X sandbox runner. It starts one locked-down container per run through the host's Docker
# daemon, so it must run on a host whose Docker has the gVisor runtime (runsc) registered,
# ideally a dedicated VM that holds no other data (see README.md).
FROM docker:27-cli
RUN apk add --no-cache python3 py3-pip \
 && python3 -m venv /opt/venv
COPY requirements.txt /app/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt
COPY sandbox.py app.py /app/
WORKDIR /app
ENV RUNNER_RUNTIME=runsc RUNNER_WORK_ROOT=/var/aepx-runs
EXPOSE 8080
CMD ["/opt/venv/bin/uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
