# Optional API image — build from repo root: docker build -t rezume-api .
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-train.txt ./
RUN pip install --no-cache-dir -r requirements-train.txt

COPY backend ./backend
COPY src ./src
COPY training ./training

ENV PYTHONPATH=/app/backend:/app
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
