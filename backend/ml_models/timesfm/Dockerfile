FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir uvicorn fastapi timesfm

COPY service.py .

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/health')"

EXPOSE 8100
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8100"]
