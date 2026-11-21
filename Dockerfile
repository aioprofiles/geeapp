FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
# ONE worker only: the bot loop and the SQLite file must not be duplicated.
CMD ["sh", "-c", "uvicorn geebot.serve:app --host 0.0.0.0 --port ${PORT:-10000}"]
