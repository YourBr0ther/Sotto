FROM python:3.11-slim AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        libespeak-ng1 && \
    rm -rf /var/lib/apt/lists/*

# Install Piper standalone binary to /opt/piper
RUN wget -q https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz -O /tmp/piper.tar.gz && \
    tar -xzf /tmp/piper.tar.gz -C /opt/ && \
    rm /tmp/piper.tar.gz && \
    chmod +x /opt/piper/piper && \
    ln -s /opt/piper/piper /usr/local/bin/piper

RUN useradd -m -r sotto && mkdir /app /models && chown -R sotto:sotto /app /models
WORKDIR /app

COPY tts/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tts/*.py ./

USER sotto

ENV PIPER_BINARY=/opt/piper/piper

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',1883)); s.close()" || exit 1

CMD ["python", "main.py"]
