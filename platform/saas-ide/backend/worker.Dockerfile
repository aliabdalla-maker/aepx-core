FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 IDE_EXTERNAL_EXECUTION_ENABLED=false
WORKDIR /app
RUN groupadd -r agent && useradd -r -g agent -d /app agent
COPY requirements.txt requirements-agent.txt ./
RUN pip install --no-cache-dir -r requirements-agent.txt
COPY app ./app
USER agent
# No entrypoint: operators must explicitly supply an audited, scoped worker command.
CMD ["python", "-c", "print('AEP-X worker disabled: no automatic execution')"]
