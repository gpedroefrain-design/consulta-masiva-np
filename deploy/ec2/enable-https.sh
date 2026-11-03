#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Ejecute este script con sudo." >&2
    exit 1
fi

if [[ "$#" -ne 1 ]]; then
    echo "Uso: sudo bash deploy/ec2/enable-https.sh <IPv4-elastica>" >&2
    exit 2
fi

PUBLIC_IPV4="$1"
python3.12 -c 'import ipaddress, sys; ipaddress.IPv4Address(sys.argv[1])' "$PUBLIC_IPV4"
APP_DIR=/opt/consulta-masiva-np

if [[ ! -s /etc/consulta-np/app.env ]]; then
    echo "Falta /etc/consulta-np/app.env; configure los secretos antes de habilitar el servicio." >&2
    exit 1
fi

/opt/certbot/bin/certbot certonly \
    --non-interactive \
    --register-unsafely-without-email \
    --agree-tos \
    --preferred-profile shortlived \
    --webroot \
    --webroot-path /var/www/letsencrypt \
    --ip-address "${PUBLIC_IPV4}"

sed "s/@PUBLIC_IPV4@/${PUBLIC_IPV4}/g" "${APP_DIR}/deploy/ec2/consulta-np-https.conf.template" \
    > /etc/nginx/conf.d/consulta-np.conf
nginx -t
systemctl reload nginx
systemctl enable --now consulta-np-certbot-renew.timer
systemctl enable --now consulta-np

echo "HTTPS y renovacion automatica configurados para ${PUBLIC_IPV4}."
