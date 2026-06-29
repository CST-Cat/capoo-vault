FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY search_server.py build_index.py ./
COPY data/ data/
COPY annotations/gifs/ annotations/gifs/
COPY annotations/batches.json annotations/batches.json

ENV PORT=8989
ENV VAULT_DIR=/app/gifs-vault
EXPOSE 8989

CMD ["python", "search_server.py"]
