#!/bin/bash
set -e

APPLIANCE=/tmp/appliance

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    postgresql postgresql-client redis-server nginx \
    python3 python3-venv python3-dev libpq-dev \
    avahi-daemon avahi-utils git curl python3-zeroconf

systemctl enable postgresql redis-server nginx avahi-daemon
sed -i 's/^hosts:.*/hosts: files mdns4_minimal [NOTFOUND=return] dns myhostname/' /etc/nsswitch.conf

mkdir -p /opt/curtain/{backend,venv,curtain,curtainptm}
mkdir -p /var/log/curtain

useradd -r -s /usr/sbin/nologin -M -d /opt/curtain curtain-svc || true
usermod -aG www-data curtain-svc

service postgresql start
su - postgres -c "psql -c \"CREATE USER curtain_user WITH PASSWORD 'curtain_pass';\"" || true
su - postgres -c "psql -c \"CREATE DATABASE curtain_db OWNER curtain_user;\"" || true
su - postgres -c "psql -c \"ALTER USER curtain_user CREATEDB;\"" || true

python3 -m venv /opt/curtain/venv
/opt/curtain/venv/bin/pip install --upgrade pip --quiet

git clone --depth 1 --branch "${BACKEND_REF}" \
    https://github.com/noatgnu/curtainbe.git /opt/curtain/backend

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

mkdir -p /etc/ssl/curtain
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/ssl/curtain/curtain.key \
    -out /etc/ssl/curtain/curtain.crt \
    -subj "/CN=curtain.local/O=Curtain Appliance" \
    -addext "subjectAltName=DNS:curtain.local,DNS:curtainptm.local,DNS:localhost,IP:127.0.0.1"
chmod 640 /etc/ssl/curtain/curtain.key

mkdir -p /etc/nginx/snippets
cp "$APPLIANCE/nginx/curtain-ssl.conf"      /etc/nginx/snippets/curtain-ssl.conf
cp "$APPLIANCE/nginx/curtain-upstream.conf" /etc/nginx/conf.d/curtain-upstream.conf
cp "$APPLIANCE/nginx/curtain.conf"          /etc/nginx/sites-available/curtain.conf
cp "$APPLIANCE/nginx/curtainptm.conf"       /etc/nginx/sites-available/curtainptm.conf
ln -sf /etc/nginx/sites-available/curtain.conf    /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/curtainptm.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t

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
systemctl enable curtain-firstboot curtain-backend curtain-rqworker curtain-ptm-mdns

chown -R curtain-svc:curtain-svc /opt/curtain /var/log/curtain
chown root:curtain-svc /opt/curtain/.env
chmod 640 /opt/curtain/.env

service postgresql restart
systemctl start nginx redis-server
