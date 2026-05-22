#!/bin/bash -e
set -e

echo "=== CURTAIN LITE: applying low-RAM optimisations ==="

cat > /etc/systemd/system/curtain-backend.service << 'UNITEOF'
[Unit]
Description=Curtain Django Backend
After=network.target postgresql.service redis-server.service curtain-firstboot.service
Requires=postgresql.service redis-server.service
Wants=curtain-firstboot.service

[Service]
Type=simple
User=curtain-svc
Group=curtain-svc
WorkingDirectory=/opt/curtain/backend
EnvironmentFile=/opt/curtain/.env
ExecStart=/opt/curtain/venv/bin/gunicorn curtainbe.asgi:application \
    --bind 127.0.0.1:8000 --workers 1 --threads 2 --timeout 300 \
    -k uvicorn.workers.UvicornWorker --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF

PG_CONF=$(find /etc/postgresql -name "postgresql.conf" 2>/dev/null | head -1)
if [ -n "$PG_CONF" ]; then
    printf '\n# Lite: tuned for 512 MB RAM\nshared_buffers = 32MB\neffective_cache_size = 128MB\nwork_mem = 2MB\nmaintenance_work_mem = 16MB\nmax_connections = 20\nmax_wal_size = 64MB\nwal_buffers = 4MB\n' \
        >> "$PG_CONF"
fi

if [ ! -f /swapfile ]; then
    dd if=/dev/zero of=/swapfile bs=1M count=512 status=none
    chmod 600 /swapfile
    mkswap /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "=== CURTAIN LITE: done ==="
