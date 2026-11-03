from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
DESPLIEGUE = RAIZ / "deploy" / "ec2"


def texto(nombre: str) -> str:
    return (DESPLIEGUE / nombre).read_text(encoding="utf-8")


def test_servicio_app_protegido_y_loopback():
    servicio = texto("consulta-np.service")
    assert "User=consulta-np" in servicio
    assert "EnvironmentFile=/etc/consulta-np/app.env" in servicio
    assert "Environment=HOST=127.0.0.1" in servicio
    assert "Environment=APP_REQUIRE_LOGIN=true" in servicio
    assert "Environment=APP_COOKIE_SECURE=true" in servicio
    assert "Environment=APP_TRUST_PROXY=true" in servicio
    assert "ExecStart=/opt/consulta-masiva-np/.venv/bin/python run.py" in servicio
    assert "TDX_PASSWORD=" not in servicio


def test_nginx_solo_publica_https_y_proxy_sobrescribe_ip():
    http = texto("consulta-np-http.conf.template")
    https = texto("consulta-np-https.conf.template")
    assert "location ^~ /.well-known/acme-challenge/" in http
    assert "return 308 https://@PUBLIC_IPV4@$request_uri;" in http
    assert "proxy_pass" not in http
    assert "listen 443 ssl default_server;" in https
    assert "proxy_pass http://127.0.0.1:8000;" in https
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in https
    assert "proxy_read_timeout 660s;" in https
    assert "proxy_send_timeout 660s;" in https
    assert "client_max_body_size 11m;" in https
    assert "proxy_buffering off;" in https


def test_renovacion_de_certificado_ip_es_automatica():
    renovacion = texto("consulta-np-certbot-renew.service")
    timer = texto("consulta-np-certbot-renew.timer")
    emision = texto("enable-https.sh")
    assert "certbot renew --quiet" in renovacion
    assert "systemctl reload nginx" in renovacion
    assert "OnCalendar=*-*-* 00,12:00:00" in timer
    assert "--preferred-profile shortlived" in emision
    assert "--ip-address" in emision


def test_instalador_copia_solo_archivos_necesarios_y_no_envia_env():
    instalador = texto("install.sh")
    for entrada in ("run.py", "requirements.txt", "consulta_np", "deploy/ec2/."):
        assert entrada in instalador
    assert 'cp -a "${APP_DIR}/."' not in instalador
    assert 'cp -a "${APP_DIR}/.env"' not in instalador
    assert "TDX_PASSWORD=" not in instalador
