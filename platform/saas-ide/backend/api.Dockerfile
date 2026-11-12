FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 IDE_EXTERNAL_EXECUTION_ENABLED=false IDE_MCP_EXECUTION_ENABLED=false
WORKDIR /app
RUN groupadd -r aepx && useradd -r -g aepx -d /app aepx
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
USER aepx
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers=false"]
