FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 powerpay \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R powerpay:powerpay /app

USER powerpay

EXPOSE 8000

CMD ["gunicorn", "powerpayerp.wsgi:application", "--config", "deploy/gunicorn.conf.py"]
