FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY edge ./edge
COPY contracts ./contracts
RUN useradd -r -u 10001 edge && mkdir -p /app/data && chown -R edge /app/data
USER edge
ENV EDGE_DATA_DIR=/app/data
EXPOSE 8001
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health')"
CMD ["python", "-m", "uvicorn", "edge.main:app", "--host", "0.0.0.0", "--port", "8001"]
