FROM python:3.11-slim AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -r sotto && mkdir /app && chown sotto:sotto /app
WORKDIR /app

COPY transcription/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY transcription/*.py ./

USER sotto

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',1883)); s.close()" || exit 1

CMD ["python", "main.py"]
