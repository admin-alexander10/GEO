#!/usr/bin/env sh
# Uso (dentro de deploy/):  API_DOMAIN=api.TU-DOMINIO sh generar_config_frontend.sh
# Crea deploy/config.js: copia de frontend/js/config.js apuntando a tu API.
# No modifica el original.
set -e
: "${API_DOMAIN:?Define API_DOMAIN}"
sed -E '/API_HOSTS: \[/,/\],/c\    API_HOSTS: ["https://'"$API_DOMAIN"'"],' ../frontend/js/config.js > config.js
grep -n "API_HOSTS" config.js
