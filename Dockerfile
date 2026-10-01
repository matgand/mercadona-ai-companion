FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GEMINI_MODEL=gemini-3.8-flash \
    ALLOWED_USERS="matgand@gmail.com,mgandolfi@google.com,andrea.anaut@gmail.com,mattia@mgandolfi.altostrat.com"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /usr/sbin/nologin appuser && \
    mkdir -p /app/data && \
    chmod 700 /app/data && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

CMD ["python3", "server.py"]
