FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SOLARPI_API_HOST=0.0.0.0 \
    SOLARPI_API_PORT=8000 \
    SOLARPI_DATABASE=/app/data/solarpi.sqlite3

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 solarpi \
    && useradd --uid 10001 --gid solarpi --no-create-home solarpi \
    && mkdir /app/data \
    && chown solarpi:solarpi /app/data

COPY solarpi/ ./solarpi/
COPY web/ ./web/

USER solarpi
EXPOSE 8000
# The original server handles KeyboardInterrupt and closes its worker threads.
STOPSIGNAL SIGINT
CMD ["python", "-m", "solarpi.main"]
