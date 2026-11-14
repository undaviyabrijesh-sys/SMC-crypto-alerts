FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    DATA_DIR=/data/market_data \
    STATE_PATH=/data/state.json \
    QUANT_RESEARCH_PATH=/data/research/quant_signals.jsonl \
    HEARTBEAT_PATH=/data/worker_heartbeat.json \
    WORKER_INTERVAL_SECONDS=300

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
VOLUME ["/data"]
CMD ["python", "-u", "worker.py"]
