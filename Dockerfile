FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 libjpeg62-turbo libxml2 libxslt1.1 shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY . .
RUN DJANGO_ENV=production \
    DJANGO_DEBUG=False \
    DJANGO_SECRET_KEY=build-only-not-for-runtime-123456789012345678901234567890 \
    DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgresql://build:build@localhost:5432/build \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 10001 nyansa && chown -R nyansa:nyansa /app
USER nyansa

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live/', timeout=3)"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
