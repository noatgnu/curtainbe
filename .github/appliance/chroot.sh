#!/bin/bash -e

echo "=== CURTAIN: installing packages ==="
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl gpg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor -o /usr/share/keyrings/postgresql-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/postgresql-keyring.gpg] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    postgresql-16 postgresql-client-16 redis-server nginx \
    python3 python3-venv python3-dev libpq-dev \
    avahi-daemon avahi-utils git python3-zeroconf

systemctl --root=/ enable postgresql redis-server nginx avahi-daemon
sed -i 's/^hosts:.*/hosts: files mdns4_minimal [NOTFOUND=return] dns myhostname/' /etc/nsswitch.conf

echo "=== CURTAIN: creating users and directories ==="
mkdir -p /opt/curtain/{venv,curtain,curtainptm}
mkdir -p /var/log/curtain

useradd -r -s /usr/sbin/nologin -M -d /opt/curtain curtain-svc || true
usermod -aG www-data curtain-svc
useradd -m -s /bin/bash curtain || true
echo 'curtain:curtain' | chpasswd
usermod -aG sudo curtain

echo "=== CURTAIN: setting up PostgreSQL ==="
service postgresql start || \
    pg_ctlcluster "$(pg_lsclusters -h | head -1 | awk '{print $1, $2}')" start
su - postgres -c "psql -c \"CREATE USER curtain_user WITH PASSWORD 'curtain_pass';\"" || true
su - postgres -c "psql -c \"CREATE DATABASE curtain_db OWNER curtain_user;\"" || true
su - postgres -c "psql -c \"ALTER USER curtain_user CREATEDB;\"" || true
PG_HBA=$(su - postgres -c "psql -t -c 'SHOW hba_file;'" | tr -d ' ')
sed -i 's/local[[:space:]]\+all[[:space:]]\+all[[:space:]]\+peer/local   all             all                                     md5/' "$PG_HBA"
sed -i 's/host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+127\.0\.0\.1\/32[[:space:]]\+scram-sha-256/host    all             all             127.0.0.1\/32            md5/' "$PG_HBA"
service postgresql restart || \
    pg_ctlcluster "$(pg_lsclusters -h | head -1 | awk '{print $1, $2}')" restart

echo "=== CURTAIN: Python venv ==="
python3 -m venv /opt/curtain/venv
/opt/curtain/venv/bin/pip install --upgrade pip --quiet
/opt/curtain/venv/bin/pip install -r /opt/curtain/backend/requirements.txt --quiet
/opt/curtain/venv/bin/pip install gunicorn "uvicorn[standard]" psycopg2-binary --quiet

cat > /opt/curtain/.env << 'DOTENV'
WORKING_ENV=PRODUCTION
POSTGRES_NAME=curtain_db
POSTGRES_USER=curtain_user
POSTGRES_PASSWORD=curtain_pass
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
SECRET_KEY=CHANGE-ON-FIRST-BOOT
DJANGO_ALLOWED_HOSTS=curtain.local,curtainptm.local,localhost,127.0.0.1
DJANGO_CORS_WHITELIST=http://curtain.local,https://curtain.local,http://curtainptm.local,https://curtainptm.local,http://localhost
CURTAIN_ALLOW_NON_USER_POST=1
CURTAIN_DEFAULT_USER_LINK_LIMIT=100
CURTAIN_DEFAULT_USER_CAN_POST=1
DOTENV

cd /opt/curtain/backend
set -a; source /opt/curtain/.env; set +a
/opt/curtain/venv/bin/python manage.py migrate --noinput
/opt/curtain/venv/bin/python manage.py collectstatic --noinput
DJANGO_SUPERUSER_USERNAME=admin \
DJANGO_SUPERUSER_EMAIL=admin@curtain.local \
DJANGO_SUPERUSER_PASSWORD=curtain \
/opt/curtain/venv/bin/python manage.py createsuperuser --noinput

echo "=== CURTAIN: SSL certificate ==="
mkdir -p /etc/ssl/curtain
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/ssl/curtain/curtain.key \
    -out /etc/ssl/curtain/curtain.crt \
    -subj "/CN=curtain.local/O=Curtain Appliance" \
    -addext "subjectAltName=DNS:curtain.local,DNS:curtainptm.local,DNS:localhost,IP:127.0.0.1"
chmod 640 /etc/ssl/curtain/curtain.key

echo "=== CURTAIN: nginx ==="
mkdir -p /etc/nginx/snippets

cat > /etc/nginx/snippets/curtain-ssl.conf << 'SSLEOF'
ssl_certificate     /etc/ssl/curtain/curtain.crt;
ssl_certificate_key /etc/ssl/curtain/curtain.key;
ssl_protocols       TLSv1.2 TLSv1.3;
ssl_ciphers         HIGH:!aNULL:!MD5;
SSLEOF

cat > /etc/nginx/conf.d/curtain-upstream.conf << 'UPEOF'
upstream curtain_backend {
    server 127.0.0.1:8000;
}
UPEOF

cat > /etc/nginx/sites-available/curtain.conf << 'NGXEOF'
server {
    listen 80 default_server;
    listen 443 ssl default_server;
    server_name curtain.local curtain localhost _;
    include /etc/nginx/snippets/curtain-ssl.conf;
    client_max_body_size 2G;
    root /opt/curtain/curtain;
    index index.html;
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        proxy_pass http://curtain_backend/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /admin/ {
        proxy_pass http://curtain_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://curtain_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }

    location /static/ { alias /opt/curtain/backend/staticfiles/; expires 7d; }
    location /media/  { alias /opt/curtain/backend/media/; }
}
NGXEOF

cat > /etc/nginx/sites-available/curtainptm.conf << 'NGXEOF'
server {
    listen 80;
    listen 443 ssl;
    server_name curtainptm.local curtainptm;
    include /etc/nginx/snippets/curtain-ssl.conf;
    client_max_body_size 2G;
    root /opt/curtain/curtainptm;
    index index.html;
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        proxy_pass http://curtain_backend/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /admin/ {
        proxy_pass http://curtain_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://curtain_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }

    location /static/ { alias /opt/curtain/backend/staticfiles/; expires 7d; }
    location /media/  { alias /opt/curtain/backend/media/; }
}
NGXEOF

ln -sf /etc/nginx/sites-available/curtain.conf    /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/curtainptm.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t

echo "=== CURTAIN: mDNS and services ==="
cat > /usr/local/bin/curtain-ptm-mdns << 'MDNSEOF'
#!/usr/bin/env python3
"""Publishes curtainptm.local via mDNS using zeroconf."""
import socket
import time
from zeroconf import ServiceInfo, Zeroconf


def get_local_ip() -> str:
    """Return the machine's primary outbound IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    """Register and keep alive the curtainptm.local mDNS service record."""
    ip = get_local_ip()
    zc = Zeroconf()
    info = ServiceInfo(
        "_http._tcp.local.",
        "CurtainPTM._http._tcp.local.",
        addresses=[socket.inet_aton(ip)],
        port=80,
        server="curtainptm.local.",
    )
    zc.register_service(info)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        zc.unregister_service(info)
        zc.close()


if __name__ == "__main__":
    main()
MDNSEOF
chmod +x /usr/local/bin/curtain-ptm-mdns

mkdir -p /etc/avahi/services
cat > /etc/avahi/services/curtain.service << 'AVHEOF'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name>Curtain Appliance</name>
  <service>
    <type>_http._tcp</type>
    <port>80</port>
    <txt-record>path=/</txt-record>
  </service>
</service-group>
AVHEOF

cat > /opt/curtain/first-boot.sh << 'FBEOF'
#!/bin/bash
set -e
LOG=/var/log/curtain/first-boot.log
mkdir -p /var/log/curtain
exec > >(tee -a "$LOG") 2>&1
echo "=== first-boot started $(date -u) ==="
ENV_FILE=/opt/curtain/.env
if grep -q "^SECRET_KEY=CHANGE-ON-FIRST-BOOT" "$ENV_FILE"; then
    NEW_KEY=$(openssl rand -base64 48 | tr -d '\n')
    sed -i "s|^SECRET_KEY=CHANGE-ON-FIRST-BOOT|SECRET_KEY=${NEW_KEY}|" "$ENV_FILE"
    echo "SECRET_KEY generated"
fi
echo "=== first-boot done $(date -u) ==="
FBEOF
chmod +x /opt/curtain/first-boot.sh

cat > /etc/systemd/system/curtain-firstboot.service << 'UNITEOF'
[Unit]
Description=Curtain First Boot Setup
After=network-online.target local-fs.target
Wants=network-online.target
Before=curtain-backend.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=root
ExecStart=/opt/curtain/first-boot.sh

[Install]
WantedBy=multi-user.target
UNITEOF

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
    --bind 127.0.0.1:8000 --workers 4 --timeout 300 \
    -k uvicorn.workers.UvicornWorker --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF

cat > /etc/systemd/system/curtain-rqworker.service << 'UNITEOF'
[Unit]
Description=Curtain RQ Worker
After=curtain-backend.service
Requires=curtain-backend.service

[Service]
Type=simple
User=curtain-svc
Group=curtain-svc
WorkingDirectory=/opt/curtain/backend
EnvironmentFile=/opt/curtain/.env
ExecStart=/opt/curtain/venv/bin/python manage.py rqworker default
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF

cat > /etc/systemd/system/curtain-ptm-mdns.service << 'UNITEOF'
[Unit]
Description=Publish curtainptm.local mDNS record
After=network-online.target avahi-daemon.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/curtain-ptm-mdns
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl --root=/ enable curtain-firstboot curtain-backend curtain-rqworker curtain-ptm-mdns

mkdir -p /etc/systemd/resolved.conf.d
printf '[Resolve]\nMulticastDNS=yes\n' > /etc/systemd/resolved.conf.d/mdns.conf

echo "=== CURTAIN: SD card write optimisations ==="
sed -i '/ext4/s/defaults/defaults,noatime/' /etc/fstab
printf 'tmpfs\t/tmp\ttmpfs\tdefaults,noatime,nosuid,size=128m\t0 0\n' >> /etc/fstab

mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=64M\n' \
    > /etc/systemd/journald.conf.d/curtain.conf

printf '\nsave ""\nappendonly no\n' >> /etc/redis/redis.conf

PG_CONF=$(find /etc/postgresql -name "postgresql.conf" 2>/dev/null | head -1)
if [ -n "$PG_CONF" ]; then
    printf '\nsynchronous_commit = off\ncheckpoint_completion_target = 0.9\nmax_wal_size = 256MB\nwal_buffers = 16MB\n' \
        >> "$PG_CONF"
fi

sed -i 's|access_log /var/log/nginx/access.log;|access_log off;|' /etc/nginx/nginx.conf

chown -R curtain-svc:curtain-svc /opt/curtain /var/log/curtain
chown root:curtain-svc /opt/curtain/.env
chmod 640 /opt/curtain/.env

echo "=== CURTAIN: stopping services ==="
service postgresql stop || \
    pg_ctlcluster "$(pg_lsclusters -h | head -1 | awk '{print $1, $2}')" stop || true

echo "=== CURTAIN: chroot done ==="
