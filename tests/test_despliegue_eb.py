"""Artefactos de despliegue en AWS Elastic Beanstalk (sin conectarse a AWS)."""
import io
import json
import re
import zipfile
from pathlib import Path

import pytest

import empaquetar_eb
from consulta_np.config import ErrorConfiguracion, cargar_configuracion
from conftest import ENV_FICTICIO

RAIZ = Path(__file__).resolve().parent.parent
SECRETOS = {"APP_SECRET_KEY", "APP_ACCESS_PASSWORD", "TDX_USERNAME", "TDX_PASSWORD", "TDX_CLI_ID"}


def opciones() -> dict[str, dict[str, str]]:
    datos = json.loads((RAIZ / ".ebextensions" / "01_consulta_np.config").read_text(encoding="utf-8"))
    resultado: dict[str, dict[str, str]] = {}
    for opcion in datos["option_settings"]:
        resultado.setdefault(opcion["namespace"], {})[opcion["option_name"]] = opcion["value"]
    return resultado


def env_eb() -> dict[str, str]:
    return opciones()["aws:elasticbeanstalk:application:environment"]


def nginx() -> dict[str, str]:
    texto = (RAIZ / ".platform" / "nginx" / "conf.d" / "consulta_np.conf").read_text(encoding="utf-8")
    return dict(re.findall(r"^(\w+)\s+([^;]+);", texto, re.MULTILINE))


def test_procfile_arranca_run_py_con_lf():
    assert (RAIZ / "Procfile").read_bytes() == b"web: python run.py\n"


def test_config_eb_sin_secretos_y_produccion_segura():
    env = env_eb()
    assert not SECRETOS & env.keys()
    assert env["HOST"] == "0.0.0.0" and env["PORT"] == "8000"
    assert env["APP_REQUIRE_LOGIN"] == "true" and env["APP_COOKIE_SECURE"] == "true"
    texto = (RAIZ / ".ebextensions" / "01_consulta_np.config").read_text(encoding="utf-8")
    assert "environmentsecrets" not in texto and "arn:aws" not in texto


def test_config_eb_valida_con_secretos_del_servidor():
    config = cargar_configuracion({**ENV_FICTICIO, "APP_COOKIE_SECURE": "", **env_eb()})
    assert config.requiere_login is True and config.cookie_secure is True and config.host == "0.0.0.0"
    with pytest.raises(ErrorConfiguracion, match="loopback"):
        cargar_configuracion({**ENV_FICTICIO, **env_eb(), "APP_REQUIRE_LOGIN": "false"})
    sin_password = {**ENV_FICTICIO, **env_eb()}
    sin_password.pop("APP_ACCESS_PASSWORD")
    with pytest.raises(ErrorConfiguracion, match="APP_ACCESS_PASSWORD"):
        cargar_configuracion(sin_password)


def test_entorno_balanceado_una_instancia_y_salud():
    o = opciones()
    assert o["aws:elasticbeanstalk:environment"] == {"EnvironmentType": "LoadBalanced", "LoadBalancerType": "application"}
    assert o["aws:autoscaling:asg"] == {"MinSize": "1", "MaxSize": "1"}
    assert o["aws:elasticbeanstalk:environment:process:default"]["HealthCheckPath"] == "/salud"


def test_timeouts_y_tamano_coherentes():
    presupuesto = int(env_eb()["TIEMPO_MAXIMO_SEGUNDOS"])
    conf = nginx()
    lectura = int(conf["proxy_read_timeout"].rstrip("s"))
    envio = int(conf["proxy_send_timeout"].rstrip("s"))
    idle_alb = int(opciones()["aws:elbv2:loadbalancer"]["IdleTimeout"])
    assert presupuesto + 60 <= lectura == envio < idle_alb <= 3600
    assert int(conf["client_max_body_size"].rstrip("m")) > int(env_eb()["MAX_UPLOAD_MB"])


def test_salud_sin_login_por_http(config):
    from consulta_np import create_app

    r = create_app(config).test_client().get("/salud", environ_base={"REMOTE_ADDR": "10.0.0.5"})
    assert r.status_code == 200 and r.get_data(as_text=True) == "ok"


def test_ebignore_excluye_secretos_y_conserva_codigo():
    patrones = {
        linea.strip() for linea in (RAIZ / ".ebignore").read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.startswith("#")
    }
    for requerido in (".git/", ".env", ".env.*", ".venv/", "tests/", "*.zip", "*.xlsx", "__pycache__/"):
        assert requerido in patrones
    for necesario in ("Procfile", "run.py", "requirements.txt", "consulta_np", ".ebextensions", ".platform"):
        assert not any(p.strip("/").startswith(necesario) for p in patrones if not p.startswith("!"))


def test_paquete_lista_blanca_en_raiz():
    buffer = io.BytesIO()
    archivos = empaquetar_eb.crear_zip(buffer)
    nombres = zipfile.ZipFile(buffer).namelist()
    assert nombres == archivos
    for esperado in ("Procfile", "run.py", "requirements.txt", "consulta_np/__init__.py",
                     "consulta_np/templates/index.html", "consulta_np/static/app.js",
                     ".ebextensions/01_consulta_np.config", ".platform/nginx/conf.d/consulta_np.conf"):
        assert esperado in nombres
    assert all("\\" not in n and not n.startswith(("/", "consulta-masiva-np/")) for n in nombres)
    prohibido = re.compile(r"(^|/)(\.env|\.venv|\.git|tests|__pycache__)(/|$|\.)|\.pyc$")
    assert not [n for n in nombres if prohibido.search(n)]


@pytest.mark.parametrize("ruta", [".env", "consulta_np/.env.produccion", ".platform/.env/x",
                                  "consulta_np/datos.xlsx", ".ebextensions/clave.pem", ".venv/x.py", "a/b.zip"])
def test_paquete_rechaza_secretos_y_datos(ruta):
    with pytest.raises(empaquetar_eb.ErrorPaquete, match="no permitido"):
        empaquetar_eb.validar_ruta(ruta)
    empaquetar_eb.validar_ruta("consulta_np/static/app.js")
