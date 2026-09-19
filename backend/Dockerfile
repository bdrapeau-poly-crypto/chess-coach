FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STOCKFISH_PATH=/usr/games/stockfish

RUN apt-get update \
    && apt-get install --yes --no-install-recommends stockfish \
    && test -x /usr/games/stockfish \
    && printf 'quit\n' | /usr/games/stockfish >/dev/null \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --requirement requirements.txt
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
