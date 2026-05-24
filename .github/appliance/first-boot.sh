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
MACHINE_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -n "$MACHINE_IP" ] && [ "$MACHINE_IP" != "127.0.0.1" ]; then
    if ! grep -q ",${MACHINE_IP}" "$ENV_FILE" && ! grep -q "=${MACHINE_IP}," "$ENV_FILE"; then
        sed -i "s|^DJANGO_ALLOWED_HOSTS=\(.*\)|DJANGO_ALLOWED_HOSTS=\1,${MACHINE_IP}|" "$ENV_FILE"
        sed -i "s|^DJANGO_CORS_WHITELIST=\(.*\)|DJANGO_CORS_WHITELIST=\1,http://${MACHINE_IP},https://${MACHINE_IP}|" "$ENV_FILE"
        echo "Added ${MACHINE_IP} to ALLOWED_HOSTS and CORS whitelist"
    fi
fi

echo "=== first-boot done $(date -u) ==="
