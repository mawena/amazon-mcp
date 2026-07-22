FROM python:3.12-slim

WORKDIR /app

# Chemin dédié pour les navigateurs Playwright (hors ~/.cache, doit rester
# accessible au runtime — la variable est donc conservée dans l'image).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY pyproject.toml ./
COPY amazon_mcp ./amazon_mcp
RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium \
    && rm -rf /root/.cache/pip

ENV DB_PATH=/data/amazon.db
EXPOSE 8321
CMD ["python", "-m", "amazon_mcp.server"]
