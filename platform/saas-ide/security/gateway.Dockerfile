# Egress gateway for the isolated AI agent worker (HTTPS CONNECT only, allowlisted hosts).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /gateway
RUN groupadd -r gateway && useradd -r -g gateway -d /gateway gateway
COPY egress_gateway.py ./
USER gateway
EXPOSE 8080
CMD ["python", "egress_gateway.py"]
