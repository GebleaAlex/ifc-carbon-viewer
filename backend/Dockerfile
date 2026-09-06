FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.12.*

WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY app ./app
COPY scripts ./scripts
COPY samples ./samples

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

ENV IFC_DATA_DIR=/app/data \
    IFC_CORS_ORIGINS=http://localhost:5173,http://localhost:8080

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
