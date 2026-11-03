#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Ejecute este script con sudo." >&2
    exit 1
fi

if [[ "$#" -ne 1 ]]; then
    echo "Uso: sudo bash deploy/ec2/install.sh <IPv4-elastica>" >&2
    exit 2
fi

PUBLIC_IPV4="$1"
python3 -c 'import ipaddress, sys; ipaddress.IPv4Address(sys.argv[1])' "$PUBLIC_IPV4"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"

if [[ ! -f "${APP_DIR}/run.py" || ! -f "${APP_DIR}/requirements.txt" ]]; then
    echo "No se encontro el codigo de la aplicacion en ${APP_DIR}." >&2
    exit 1
fi

dnf install -y nginx python3.12 python3.12-pip

if ! id consulta-np >/dev/null 2>&1; then
    useradd --system --home-dir /opt/consulta-masiva-np --shell /sbin/nologin consulta-np
fi

install -d -o root -g root -m 0755 /opt/consulta-masiva-np
install -d -o root -g root -m 0755 /opt/consulta-masiva-np/deploy/ec2
cp -a "${APP_DIR}/run.py" /opt/consulta-masiva-np/
cp -a "${APP_DIR}/requirements.txt" /opt/consulta-masiva-np/
cp -a "${APP_DIR}/consulta_np" /opt/consulta-masiva-np/
cp -a "${APP_DIR}/deploy/ec2/." /opt/consulta-masiva-np/deploy/ec2/

python3.12 -m venv /opt/consulta-masiva-np/.venv
/opt/consulta-masiva-np/.venv/bin/pip install --disable-pip-version-check -r /opt/consulta-masiva-np/requirements.txt

python3.12 -m venv /opt/certbot
/opt/certbot/bin/pip install --disable-pip-version-check 'certbot>=5.4,<6'

install -d -o root -g root -m 0755 /etc/consulta-np
install -d -o root -g root -m 0755 /var/www/letsencrypt
install -o root -g root -m 0644 "${APP_DIR}/deploy/ec2/consulta-np.service" /etc/systemd/system/consulta-np.service
install -o root -g root -m 0644 "${APP_DIR}/deploy/ec2/consulta-np-certbot-renew.service" /etc/systemd/system/consulta-np-certbot-renew.service
install -o root -g root -m 0644 "${APP_DIR}/deploy/ec2/consulta-np-certbot-renew.timer" /etc/systemd/system/consulta-np-certbot-renew.timer
sed "s/@PUBLIC_IPV4@/${PUBLIC_IPV4}/g" "${APP_DIR}/deploy/ec2/consulta-np-http.conf.template" \
    > /etc/nginx/conf.d/consulta-np.conf

nginx -t
systemctl daemon-reload
systemctl enable --now nginx
systemctl enable consulta-np

echo "Preparacion lista. Nginx solo sirve el reto ACME y redirige el resto a HTTPS."
echo "Cree /etc/consulta-np/app.env con sudoedit; no pegue secretos en comandos."
echo "Despues ejecute: sudo bash ${APP_DIR}/deploy/ec2/enable-https.sh ${PUBLIC_IPV4}"
