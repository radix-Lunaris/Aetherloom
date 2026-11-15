ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}
WORKDIR /app
COPY server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY aetherloom /app/aetherloom
RUN useradd --uid 10001 --create-home aetherloom && mkdir /data && chown aetherloom:aetherloom /data
USER aetherloom
ENV AETHERLOOM_DATA=/data PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health',timeout=3)"
CMD ["uvicorn","aetherloom.server:create_app","--factory","--host","0.0.0.0","--port","8765","--workers","1"]

