FROM python:3.11-slim

WORKDIR /app

# 安装 uv
RUN pip install --no-cache-dir uv

# 先复制依赖声明，利用 Docker 层缓存
COPY pyproject.toml .

# 安装全部依赖（含 dev）
RUN uv pip install --system -e ".[dev]"

# 开发模式：代码通过 docker-compose volume 挂载，不在此 COPY
# 生产模式可在此追加: COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
