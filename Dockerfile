FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    curl \
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    streamlink \
    yt-dlp

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir \
    -r requirements.txt

COPY . .

RUN mkdir -p /data/recordings

CMD ["python", "bot.py"]