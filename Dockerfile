FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd --system cbd && useradd --system --gid cbd --home-dir /app cbd
COPY --chown=cbd:cbd app ./app
COPY --chown=cbd:cbd alembic ./alembic
COPY --chown=cbd:cbd alembic.ini ./
USER cbd
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

FROM base AS dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/app"]

FROM base AS test
USER root
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=cbd:cbd pytest.ini ./
COPY --chown=cbd:cbd tests ./tests
USER cbd
ENV ENVIRONMENT=test
HEALTHCHECK NONE
CMD ["python", "-m", "pytest", "-m", "not integration", "-p", "no:cacheprovider"]

FROM base AS production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
