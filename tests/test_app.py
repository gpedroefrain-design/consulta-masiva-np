import csv
import io

import pytest

from consulta_np import create_app
from consulta_np.config import ErrorConfiguracion, cargar_configuracion
from consulta_np.tdx import ClienteTdx, ErrorApi
from conftest import PASSWORD, SesionFalsa, eco_encontrados, extraer_csrf, respuesta, xlsx


def fabrica(sesion):
    def crear(api):
        from dataclasses import replace
        return ClienteTdx(replace(api, pausa_base_reintento=0), sesion=sesion, dormir=lambda s: None)
    return crear


@pytest.fixture
def sesion_api():
    return SesionFalsa(consultas=[eco_encontrados])


@pytest.fixture
def cliente_web(config, sesion_api):
    app = create_app(config, cliente_factory=fabrica(sesion_api))
    return app.test_client()


def login(cliente, password=PASSWORD):
    csrf = extraer_csrf(cliente.get("/").get_data(as_text=True))
    return cliente.post("/login", data={"csrf_token": csrf, "password": password})


def subir(cliente, contenido, nombre="entrada.xlsx", csrf=None, fetch=False):
    if csrf is None:
        csrf = extraer_csrf(cliente.get("/").get_data(as_text=True))
    headers = {"X-Requested-With": "fetch"} if fetch else {}
    return cliente.post("/consultar", data={"csrf_token": csrf, "archivo": (io.BytesIO(contenido), nombre)},
                        content_type="multipart/form-data", headers=headers)


@pytest.mark.parametrize("faltante", ["APP_SECRET_KEY", "APP_ACCESS_PASSWORD", "TDX_USERNAME", "TDX_PASSWORD", "TDX_CLI_ID"])
def test_falla_cerrado_sin_configuracion(env, faltante):
    env.pop(faltante)
    with pytest.raises(ErrorConfiguracion, match=faltante):
        cargar_configuracion(env)


def test_configuracion_debil_o_insegura(env):
    with pytest.raises(ErrorConfiguracion):
        cargar_configuracion({**env, "APP_SECRET_KEY": "corta"})
    with pytest.raises(ErrorConfiguracion):
        cargar_configuracion({**env, "APP_ACCESS_PASSWORD": "corta"})
    with pytest.raises(ErrorConfiguracion):
        cargar_configuracion({**env, "TDX_QUERY_URL": "http://inseguro"})
    with pytest.raises(ErrorConfiguracion):
        create_app(cargar_configuracion({}))


def test_login_requiere_csrf_y_contrasena(cliente_web):
    cliente_web.get("/")
    assert cliente_web.post("/login", data={"password": PASSWORD}).status_code == 400
    assert login(cliente_web, "incorrecta-000").status_code == 401
    r = login(cliente_web)
    assert r.status_code == 303
    html = cliente_web.get("/").get_data(as_text=True)
    assert "NUMERO_PARTE" in html and "contrasena-ficticia" not in html and "cliente-ficticio" not in html


def test_limite_intentos_login(cliente_web):
    for _ in range(5):
        assert login(cliente_web, "incorrecta-000").status_code == 401
    assert login(cliente_web).status_code == 429


def test_origen_cruzado_rechazado(cliente_web):
    csrf = extraer_csrf(cliente_web.get("/").get_data(as_text=True))
    r = cliente_web.post("/login", data={"csrf_token": csrf, "password": PASSWORD}, headers={"Origin": "https://malo.example"})
    assert r.status_code == 400


def test_consultar_requiere_sesion_y_csrf(cliente_web, sesion_api):
    assert subir(cliente_web, xlsx([["NP"], ["A1"]]), fetch=True).status_code == 401
    login(cliente_web)
    r = subir(cliente_web, xlsx([["NP"], ["A1"]]), csrf="falso", fetch=True)
    assert r.status_code == 400 and "expiro" in r.get_json()["error"]
    assert sesion_api.llamadas == []


def test_flujo_completo_excel_a_csv(cliente_web, sesion_api):
    login(cliente_web)
    r = subir(cliente_web, xlsx([["np"], ["A1"], ["b2"], [None], ["a1"], ["00123"]]))
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert r.headers["Content-Disposition"].startswith("attachment; filename=\"consulta_np_")
    datos = r.get_data()
    assert datos.startswith(b"\xef\xbb\xbf")
    filas = list(csv.reader(io.StringIO(datos.decode("utf-8-sig"))))
    assert filas[0] == ["numeroParteEnviado", "encontrado", "numeroParte", "numeroParteInterno", "fraccion",
                        "descripcionFactura", "descripcionPedimento", "pais", "unidadMedida", "marca", "modelo",
                        "tipoMercancia", "sustentoNormativo", "igiTasa", "observaciones"]
    assert b"UNSPSC" not in datos and b"99999999" not in datos
    assert [f[0] for f in filas[1:]] == ["A1", "b2", "00123"]
    assert [f[1] for f in filas[1:]] == ["1", "0", "0"]
    assert (r.headers["X-Encontrados"], r.headers["X-No-Encontrados"]) == ("1", "2")
    assert sesion_api.de("consulta")[0]["json"]["numeros"] == ["A1", "b2", "00123"]


def test_np_sin_registro_en_api(config):
    sesion = SesionFalsa(consultas=[respuesta(200, {"data": []})])
    c = create_app(config, cliente_factory=fabrica(sesion)).test_client()
    login(c)
    r = subir(c, xlsx([["NP"], ["Z9"]]))
    fila = list(csv.reader(io.StringIO(r.get_data().decode("utf-8-sig"))))[1]
    assert fila[0] == "Z9" and fila[1] == "0" and "no devolvio" in fila[-1]


def test_archivos_invalidos(cliente_web, sesion_api):
    login(cliente_web)
    r = subir(cliente_web, b"no es excel", nombre="datos.csv", fetch=True)
    assert r.status_code == 400 and ".xlsx" in r.get_json()["error"]
    r = subir(cliente_web, b"no es excel", fetch=True)
    assert r.status_code == 400 and "XLSX" in r.get_json()["error"]
    r = subir(cliente_web, xlsx([["CODIGO"], ["A"]]))
    assert r.status_code == 400 and "NUMERO_PARTE" in r.get_data(as_text=True)
    assert sesion_api.llamadas == []


def test_archivo_demasiado_grande(env):
    app = create_app(cargar_configuracion({**env, "MAX_UPLOAD_MB": "1"}))
    c = app.test_client()
    login(c)
    r = subir(c, b"PK" + b"0" * (2 * 1024 * 1024), fetch=True)
    assert r.status_code == 413 and "MB" in r.get_json()["error"]


def test_error_api_claro_sin_detalles_sensibles(config):
    sesion = SesionFalsa(consultas=[respuesta(503, {})])
    c = create_app(config, cliente_factory=fabrica(sesion)).test_client()
    login(c)
    r = subir(c, xlsx([["NP"], ["A1"]]), fetch=True)
    assert r.status_code == 502
    mensaje = r.get_json()["error"]
    assert "HTTP 503" in mensaje and "tok-1" not in mensaje and "contrasena-ficticia" not in mensaje


def test_excepcion_interna_sin_traza(config):
    def roto(api):
        raise ZeroDivisionError("detalle interno secreto")
    c = create_app(config, cliente_factory=roto).test_client()
    login(c)
    r = subir(c, xlsx([["NP"], ["A1"]]), fetch=True)
    assert r.status_code == 500
    cuerpo = r.get_data(as_text=True)
    assert "Traceback" not in cuerpo and "secreto" not in cuerpo


def test_cabeceras_seguridad_y_cookie(cliente_web):
    r = cliente_web.get("/")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_cookie_secure_por_defecto(env):
    env.pop("APP_COOKIE_SECURE")
    assert cargar_configuracion(env).cookie_secure is True


def test_logout(cliente_web):
    login(cliente_web)
    csrf = extraer_csrf(cliente_web.get("/").get_data(as_text=True))
    cliente_web.post("/logout", data={"csrf_token": csrf})
    assert subir(cliente_web, xlsx([["NP"], ["A1"]]), fetch=True).status_code == 401