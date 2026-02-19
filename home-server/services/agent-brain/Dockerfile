FROM python:3.11-slim AS base

RUN useradd -m -r sotto && mkdir /app /data && chown -R sotto:sotto /app /data
WORKDIR /app

COPY agent-brain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent brain modules
COPY agent-brain/*.py ./

# Copy sibling service clients and schema
COPY operational-db/db_client.py ./
COPY operational-db/schema.sql ./
COPY vault-manager/vault_client.py ./

USER sotto

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',1883)); s.close()" || exit 1

CMD ["python", "main.py"]
