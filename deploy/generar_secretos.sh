#!/usr/bin/env sh
# Imprime valores aleatorios para pegar en deploy/.env
echo "DB_PASSWORD=$(openssl rand -hex 16)"
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "SMS_WEBHOOK_SECRET=$(openssl rand -hex 32)"
echo "SMS_OTP_PEPPER=$(openssl rand -hex 32)"
echo "SMS_DEVICE_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')"
