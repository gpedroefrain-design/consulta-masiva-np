import io

import pytest

from consulta_np import create_app
from consulta_np.config import ErrorConfiguracion, cargar_configuracion
from consulta_np.excel import MIME_XLSX
from conftest import SesionFalsa, eco_encontrados, extraer_csrf, leer_resultados, xlsx
from test_app import fabrica, subir


@pytest.fixture
def env_local(env):
    env = {**env, "APP_REQUIRE_LOGIN": "false", "HOST": "127.0.0.1"}
    env.pop("APP_ACCESS_PASSWORD")
    return env


@pytest.fixture
def sesion_api():
    return SesionFalsa(consultas=[eco_encontrados])


@pytest.fixture
def cliente_local(env_local, sesion_api):
    return create_app(cargar_configuracion(env_local), cliente_factory=fabrica(sesion_api)).test_client()


def test_login_requerido_por_defecto(env):
    config = cargar_configuracion(env)
    assert config.requiere_login is True
    env.pop("APP_ACCESS_PASSWORD")
    with pytest.raises(ErrorConfiguracion, match="APP_ACCESS_PASSWORD"):
        cargar_configuracion(env)


def test_sin_contrasena_en_config(env_local):
    config = cargar_configuracion(env_local)
    assert config.requiere_login is False and config.access_password == ""


@pytest.mark.parametrize("valor", ["quizas", "2", "falso"])
def test_flag_invalida(env, valor):
    with pytest.raises(ErrorConfiguracion, match="APP_REQUIRE_LOGIN"):
        cargar_configuracion({**env, "APP_REQUIRE_LOGIN": valor})


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.1.2.3", "servidor.empresa.local"])
def test_bind_publico_rechazado(env_local, host):
    with pytest.raises(ErrorConfiguracion, match="loopback"):
        cargar_configuracion({**env_local, "HOST": host})


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_bind_loopback_aceptado(env_local, host):
    assert cargar_configuracion({**env_local, "HOST": host}).host == host


@pytest.mark.parametrize("faltante", ["APP_SECRET_KEY", "TDX_USERNAME", "TDX_PASSWORD", "TDX_CLI_ID"])
def test_secretos_siguen_obligatorios(env_local, faltante):
    env_local.pop(faltante)
    with pytest.raises(ErrorConfiguracion, match=faltante):
        cargar_configuracion(env_local)


def test_get_muestra_formulario_sin_contrasena(cliente_local):
    r = cliente_local.get("/")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="form-consulta"' in html and 'name="archivo"' in html
    assert 'type="password"' not in html and "Cerrar sesi" not in html
    assert "csrf_token" in html and "HttpOnly" in r.headers.get("Set-Cookie", "")


def test_login_y_logout_deshabilitados(cliente_local):
    csrf = extraer_csrf(cliente_local.get("/").get_data(as_text=True))
    assert cliente_local.post("/login", data={"csrf_token": csrf, "password": "x"}).status_code == 404
    assert cliente_local.post("/logout", data={"csrf_token": csrf}).status_code == 404


def test_post_xlsx_sin_login_y_sin_unspsc(cliente_local, sesion_api):
    r = subir(cliente_local, xlsx([["NP"], ["A1"], ["b2"]]))
    assert r.status_code == 200 and r.mimetype == MIME_XLSX
    _, filas = leer_resultados(r.get_data())
    assert "UNSPSC" not in str(filas) and "99999999" not in str(filas)
    assert [f[:2] for f in filas[1:]] == [["A1", "1"], ["b2", "0"]]
    assert sesion_api.de("consulta")[0]["json"]["numeros"] == ["A1", "b2"]


def test_csrf_invalido_rechazado(cliente_local, sesion_api):
    cliente_local.get("/")
    r = subir(cliente_local, xlsx([["NP"], ["A1"]]), csrf="falso", fetch=True)
    assert r.status_code == 400 and "expiro" in r.get_json()["error"]
    csrf = extraer_csrf(cliente_local.get("/").get_data(as_text=True))
    r = cliente_local.post("/consultar", data={"csrf_token": csrf, "archivo": (io.BytesIO(xlsx([["NP"], ["A1"]])), "e.xlsx")},
                           content_type="multipart/form-data", headers={"Origin": "https://malo.example"})
    assert r.status_code == 400
    assert sesion_api.llamadas == []


def test_validaciones_y_limites_se_mantienen(env_local, sesion_api):
    c = create_app(cargar_configuracion({**env_local, "MAX_UPLOAD_MB": "1"}), cliente_factory=fabrica(sesion_api)).test_client()
    assert subir(c, b"x", nombre="datos.csv", fetch=True).status_code == 400
    assert subir(c, b"PK" + b"0" * (2 * 1024 * 1024), fetch=True).status_code == 413
    assert sesion_api.llamadas == []


def test_peticion_remota_rechazada(cliente_local, sesion_api):
    remoto = {"REMOTE_ADDR": "10.0.0.5"}
    assert cliente_local.get("/", environ_base=remoto).status_code == 403
    r = cliente_local.get("/", environ_base=remoto, headers={"X-Forwarded-For": "127.0.0.1"})
    assert r.status_code == 403
    r = cliente_local.post("/consultar", environ_base=remoto, data={}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 403
    assert cliente_local.get("/", environ_base={"REMOTE_ADDR": "::1"}).status_code == 200
    assert sesion_api.llamadas == []


def test_con_login_no_aplica_restriccion_loopback(config):
    c = create_app(config).test_client()
    assert c.get("/", environ_base={"REMOTE_ADDR": "10.0.0.5"}).status_code == 200
