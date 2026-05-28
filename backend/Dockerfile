FROM python:3.12.13-slim

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 helix && useradd --uid 1001 --gid helix --shell /bin/false helix

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/backend

WORKDIR /app/backend

RUN mkdir -p /data && chown helix:helix /data /tmp

USER helix

EXPOSE 8000

CMD ["uvicorn", "main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
