FROM python:3.12.13-slim

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends curl gosu && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 helix && useradd --uid 1001 --gid helix --shell /bin/false helix

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/backend

WORKDIR /app/backend

RUN mkdir -p /data && chown helix:helix /data /tmp

COPY <<"EOF" /app/docker-entrypoint.sh
#!/bin/sh
chown helix:helix /data 2>/dev/null || true
exec gosu helix "$@"
EOF
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
