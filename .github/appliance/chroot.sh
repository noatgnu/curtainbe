#!/bin/bash -e

APPLIANCE=/tmp/appliance

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

cp "$APPLIANCE/env.template" /opt/curtain/.env

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
cp "$APPLIANCE/nginx/curtain-ssl.conf"      /etc/nginx/snippets/curtain-ssl.conf
cp "$APPLIANCE/nginx/curtain-upstream.conf" /etc/nginx/conf.d/curtain-upstream.conf
cp "$APPLIANCE/nginx/curtain.conf"          /etc/nginx/sites-available/curtain.conf
cp "$APPLIANCE/nginx/curtainptm.conf"       /etc/nginx/sites-available/curtainptm.conf
ln -sf /etc/nginx/sites-available/curtain.conf    /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/curtainptm.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t

echo "=== CURTAIN: mDNS and services ==="
cp "$APPLIANCE/curtain-ptm-mdns.py" /usr/local/bin/curtain-ptm-mdns
chmod +x /usr/local/bin/curtain-ptm-mdns

mkdir -p /etc/avahi/services
cp "$APPLIANCE/avahi/curtain.service" /etc/avahi/services/curtain.service

cp "$APPLIANCE/first-boot.sh" /opt/curtain/first-boot.sh
chmod +x /opt/curtain/first-boot.sh

cp "$APPLIANCE/systemd/curtain-firstboot.service" /etc/systemd/system/
cp "$APPLIANCE/systemd/curtain-backend.service"   /etc/systemd/system/
cp "$APPLIANCE/systemd/curtain-rqworker.service"  /etc/systemd/system/
cp "$APPLIANCE/systemd/curtain-ptm-mdns.service"  /etc/systemd/system/
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

rm -rf "$APPLIANCE"
echo "=== CURTAIN: chroot done ==="
