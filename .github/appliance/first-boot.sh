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
