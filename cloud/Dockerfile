FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HIVEMIND_DATA_DIR=/var/lib/hivemind \
    HIVEMIND_UPLOADS_DIR=/var/lib/hivemind/uploads

WORKDIR /app/cloud

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY cloud/requirements.txt ./requirements.txt

RUN pip install --upgrade pip && pip install -r requirements.txt

COPY cloud/ ./

RUN chmod +x scripts/start_container.sh && \
    mkdir -p /var/lib/hivemind/uploads /var/lib/hivemind/logs

EXPOSE 8000

CMD ["/bin/bash", "scripts/start_container.sh"]
