import io
import re

import pytest
from openpyxl import load_workbook

from consulta_np import create_app
from consulta_np.config import cargar_configuracion
from consulta_np.excel import generar_layout, leer_numeros_excel
from conftest import SesionFalsa, eco_encontrados, leer_resultados
from test_app import fabrica, login, subir

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def sesion_api():
    return SesionFalsa(consultas=[eco_encontrados])


@pytest.fixture
def cliente_login(config, sesion_api):
    return create_app(config, cliente_factory=fabrica(sesion_api)).test_client()


@pytest.fixture
def cliente_local(env, sesion_api):
    env = {**env, "APP_REQUIRE_LOGIN": "false", "HOST": "127.0.0.1"}
    env.pop("APP_ACCESS_PASSWORD")
    return create_app(cargar_configuracion(env), cliente_factory=fabrica(sesion_api)).test_client()


def llenar(contenido: bytes, valores) -> bytes:
    libro = load_workbook(io.BytesIO(contenido))
    hoja = libro["CONSULTA"]
    for fila, valor in enumerate(valores, start=2):
        hoja.cell(row=fila, column=1, value=valor)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_layout_vacio_con_formato_texto():
    libro = load_workbook(io.BytesIO(generar_layout()))
    assert libro.sheetnames == ["CONSULTA"]
    hoja = libro["CONSULTA"]
    assert hoja["A1"].value == "NP" and hoja["A1"].font.b
    assert hoja.max_row == 1 and hoja.max_column == 1
    assert hoja.column_dimensions["A"].number_format == "@"
    assert hoja.column_dimensions["A"].width >= 20
    assert hoja.freeze_panes == "A2"


def test_layout_llenado_roundtrip_conserva_ceros():
    r = leer_numeros_excel(llenar(generar_layout(), ["ABC-1", "00123", "0007", "abc-1"]))
    assert r.numeros == ["ABC-1", "00123", "0007"]


def verificar_descarga(r):
    assert r.status_code == 200
    assert r.mimetype == MIME_XLSX
    assert r.headers["Content-Disposition"] == 'attachment; filename="layout_consulta_np.xlsx"'
    assert r.headers["Cache-Control"] == "no-store"
    hoja = load_workbook(io.BytesIO(r.get_data()))["CONSULTA"]
    assert [[c for c in fila] for fila in hoja.iter_rows(values_only=True)] == [["NP"]]


def test_descarga_requiere_login(cliente_login, sesion_api):
    r = cliente_login.get("/layout", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 401 and r.mimetype != MIME_XLSX
    assert cliente_login.get("/layout").status_code == 401
    login(cliente_login)
    verificar_descarga(cliente_login.get("/layout"))
    assert sesion_api.llamadas == []


def test_layout_llenado_y_consultado_con_xlsx(cliente_login, sesion_api):
    login(cliente_login)
    plantilla = cliente_login.get("/layout").get_data()
    r = subir(cliente_login, llenar(plantilla, ["A1", "00123", "a1"]), nombre="layout_consulta_np.xlsx")
    assert r.status_code == 200 and r.mimetype == MIME_XLSX
    assert r.headers["Content-Disposition"].endswith('.xlsx"')
    _, filas = leer_resultados(r.get_data())
    assert [f[:3] for f in filas[1:]] == [["A1", "1", "A1"], ["00123", "0", "00123"]]
    assert sesion_api.de("consulta")[0]["json"]["numeros"] == ["A1", "00123"]


def test_descarga_sin_login_solo_loopback(cliente_local, sesion_api):
    verificar_descarga(cliente_local.get("/layout"))
    verificar_descarga(cliente_local.get("/layout", environ_base={"REMOTE_ADDR": "::1"}))
    r = cliente_local.get("/layout", environ_base={"REMOTE_ADDR": "10.0.0.5"}, headers={"X-Forwarded-For": "127.0.0.1"})
    assert r.status_code == 403 and r.mimetype != MIME_XLSX
    assert sesion_api.llamadas == []


def test_ui_enlace_layout_fuera_de_formulario_e_instrucciones_plegables(cliente_local):
    html = cliente_local.get("/").get_data(as_text=True)
    enlace = re.search(r'<a id="enlace-layout"[^>]*>Descargar layout</a>', html)
    assert enlace and 'href="/layout"' in enlace.group(0)
    formulario = re.search(r'<form id="form-consulta".*?</form>', html, re.S).group(0)
    assert "enlace-layout" not in formulario
    assert html.index("enlace-layout") < html.index('id="form-consulta"')
    plegable = re.search(r'<details class="plegable" open>(.*?)</details>', html, re.S)
    assert plegable, "instrucciones deben estar en <details open>"
    contenido = plegable.group(1)
    assert re.search(r'<summary><h2 id="titulo-instrucciones">Instrucciones</h2></summary>', contenido)
    assert "NUMERO_PARTE" in contenido and "fila 2" in contenido and "Texto" in contenido
    assert "enlace-layout" not in contenido


def test_ui_con_login_muestra_enlace_solo_autenticado(cliente_login):
    assert "Descargar layout" not in cliente_login.get("/").get_data(as_text=True)
    login(cliente_login)
    assert "Descargar layout" in cliente_login.get("/").get_data(as_text=True)


@pytest.mark.parametrize("modo", ["cliente_local", "cliente_login"])
def test_ui_textos_retirados_boton_run_y_sin_csv(modo, request):
    cliente = request.getfixturevalue(modo)
    if modo == "cliente_login":
        login(cliente)
    html = cliente.get("/").get_data(as_text=True)
    assert "Plantilla Excel vac" not in html
    assert "Modo local sin contrase" not in html and "solo accesible desde este equipo" not in html
    boton = re.search(r'<button id="boton-consultar"[^>]*>([^<]*)</button>', html)
    assert boton and boton.group(1) == "RUN" and 'type="submit"' in boton.group(0)
    assert "Consultar y descargar" not in html
    assert "csv" not in html.lower()
    assert "descarga un Excel (.xlsx)" in html
    assert '<label for="archivo">' in html and 'aria-describedby="ayuda-archivo"' in html
    assert 'role="status"' in html and 'aria-live="polite"' in html
    assert ("Cerrar sesi" in html) == (modo == "cliente_login")


def test_js_descarga_xlsx_sin_csv(cliente_local):
    js = cliente_local.get("/static/app.js").get_data(as_text=True)
    assert '"consulta_np.xlsx"' in js and "csv" not in js.lower()
    assert "boton.disabled = false" in js and 'removeAttribute("aria-busy")' in js
    assert "textContent" not in js.split("function mostrar")[0]
