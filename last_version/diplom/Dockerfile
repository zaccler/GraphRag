FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/RAGU

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
COPY RAGU ./RAGU

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY dhb ./dhb
COPY knb ./knb
COPY lms ./lms
COPY mgr ./mgr
COPY xdt ./xdt
COPY server.py ./server.py

EXPOSE 8099

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8099"]
