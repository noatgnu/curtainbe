FROM python:3.10-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN curl https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor | tee /etc/apt/trusted.gpg.d/apt.postgresql.org.gpg > /dev/null
RUN sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 7FCC7D46ACCC4CF8
RUN apt-get update && apt-get -y install postgresql-client redis-tools
WORKDIR /app
RUN mkdir "/app/media"
RUN mkdir "/app/backup"
COPY . /app/

RUN pip install -r requirements.txt
RUN python manage.py collectstatic --noinput

COPY docker/wait-for-services.sh /wait-for-services.sh
RUN chmod +x /wait-for-services.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD curl -f http://localhost:8000/ || exit 1

ENTRYPOINT ["/wait-for-services.sh"]
CMD ["gunicorn", "curtainbe.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "300", "--graceful-timeout", "30", "--max-requests", "1000", "--max-requests-jitter", "100"]
