# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Runtime packages required by the actual Telegram bot features.
# Tesseract is needed for OCR; libmagic1 is used by file validation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr \
       tesseract-ocr-eng \
       tesseract-ocr-urd \
       libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/downloads /app/logs /app/job-data \
    && chmod 755 /app/data /app/downloads /app/logs /app/job-data

# The bot is a polling application. It does not require an inbound Telegram
# webhook port, but the app exposes its local health endpoint for Docker/ops.
EXPOSE 8080

# Give the bot time to connect DB, start the health server, and finish Telegram
# bootstrap. A short start-period previously caused Docker to kill the container
# after roughly one minute of "unhealthy" probes.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT','8080') + '/health', timeout=3).read()" || exit 1

# One foreground process: the actual Telegram bot.
CMD ["python", "bot.py"]
