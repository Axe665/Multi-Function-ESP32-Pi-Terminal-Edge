# 基础镜像可用 build args 换成镜像源，默认走官方
ARG PYTHON_IMAGE=python:3.11-slim
# 依赖源同样可换：国内用 https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
FROM ${PYTHON_IMAGE}
# FROM 之前的 ARG 只对 FROM 生效，构建阶段要重新声明
ARG PIP_INDEX_URL=https://pypi.org/simple
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install --index-url ${PIP_INDEX_URL} -r requirements.txt
COPY edge ./edge
COPY contracts ./contracts
RUN useradd -r -u 10001 edge && mkdir -p /app/data && chown -R edge /app/data
USER edge
ENV EDGE_DATA_DIR=/app/data
EXPOSE 8001
# 配了 EDGE_ADMIN_TOKEN 时 /health 要鉴权；健康检查自己带上，否则容器永远 unhealthy
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import os,urllib.request;r=urllib.request.Request('http://127.0.0.1:8001/api/v1/health');t=os.environ.get('EDGE_ADMIN_TOKEN');t and r.add_header('Authorization','Bearer '+t);urllib.request.urlopen(r)"
CMD ["python", "-m", "uvicorn", "edge.main:app", "--host", "0.0.0.0", "--port", "8001"]
