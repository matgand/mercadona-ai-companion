FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV ENFORCE_IAP_JWT=1
ENV HIDE_ALLOWED_USERS_UNAUTHED=1
ENV ALLOW_LOCAL_DEV_FALLBACK=0

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd -m -u 10001 appuser

COPY server.py mercadona_service.py cookidoo_service.py gemini_planner.py campaign_service.py whatsapp_service.py /app/
COPY data/ /app/data/
COPY public/ /app/public/

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

CMD ["python3", "server.py"]
