FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TELEMETRY_CONFIG=examples/configs/dockerfiles/telemetry_docker.yaml

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /usr/sbin/nologin telemetry \
    && chown -R telemetry:telemetry /app

USER telemetry

EXPOSE 5000

CMD ["sh", "-c", "gunicorn -c gunicorn.conf.py app:app"]
