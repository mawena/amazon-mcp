FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY amazon_mcp ./amazon_mcp
RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium \
    && rm -rf /root/.cache

ENV DB_PATH=/data/amazon.db
EXPOSE 8321
CMD ["python", "-m", "amazon_mcp.server"]
