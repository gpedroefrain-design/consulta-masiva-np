from dataclasses import replace

import pytest
import requests

from consulta_np.tdx import ClienteTdx, ErrorApi, RespuestaInesperada, extraer_resultados
from conftest import SesionFalsa, eco_encontrados, respuesta


def cliente(config, sesion, **cambios):
    api = replace(config.api, pausa_base_reintento=0, **cambios)
    pausas = []
    c = ClienteTdx(api, sesion=sesion, dormir=pausas.append)
    c.pausas = pausas
    return c


def test_extraer_resultados_formas():
    fila = {"numeroParte": "A"}
    assert extraer_resultados([fila]) == [fila]
    for clave in ("data", "results", "resultados", "resultado", "items", "numeros", "response"):
        assert extraer_resultados({clave: [fila]}) == [fila]
    assert extraer_resultados({"data": {"items": [fila]}}) == [fila]
    assert extraer_resultados({"data": [], "results": [fila]}) == [fila]
    assert extraer_resultados({"data": []}) == []
    assert extraer_resultados({"otra": [fila]}) is None
    assert extraer_resultados(["texto"]) is None
    assert extraer_resultados("x") is None


def test_lotes_payload_y_bearer(config):
    sesion = SesionFalsa(consultas=[eco_encontrados])
    c = cliente(config, sesion, tamano_lote=2)
    r = c.consultar(["A1", "B2", "A3"])
    assert [x["numeroParteEnviado"] for x in r] == ["A1", "B2", "A3"]
    consultas = sesion.de("consulta")
    assert [x["json"]["numeros"] for x in consultas] == [["A1", "B2"], ["A3"]]
    assert all(x["json"]["cli_id"] == "cliente-ficticio" for x in consultas)
    assert consultas[0]["headers"]["Authorization"] == "Bearer tok-1"
    assert sesion.de("login")[0]["data"] == {"username": "usuario-ficticio", "password": "contrasena-ficticia"}
    assert len(sesion.de("login")) == 1


def test_renueva_token_en_401(config):
    sesion = SesionFalsa(
        login=[respuesta(200, {"data": {"access_token": "tok-1"}}), respuesta(200, {"data": {"access_token": "tok-2"}})],
        consultas=[respuesta(401, {}), eco_encontrados],
    )
    r = cliente(config, sesion).consultar(["A1"])
    assert r[0]["encontrado"] == 1
    assert len(sesion.de("login")) == 2
    assert sesion.de("consulta")[1]["headers"]["Authorization"] == "Bearer tok-2"


def test_401_persistente_limitado(config):
    sesion = SesionFalsa(consultas=[respuesta(401, {})])
    with pytest.raises(ErrorApi, match="3 intentos"):
        cliente(config, sesion).consultar(["A1"])
    assert len(sesion.de("consulta")) == 3


def test_reintentos_limitados_en_5xx(config):
    sesion = SesionFalsa(consultas=[respuesta(503, {})])
    c = cliente(config, sesion)
    with pytest.raises(ErrorApi, match="HTTP 503"):
        c.consultar(["A1"])
    assert len(sesion.de("consulta")) == 3
    assert len(c.pausas) == 2


def test_timeout_reintenta_y_recupera(config):
    sesion = SesionFalsa(consultas=[requests.Timeout("lento"), eco_encontrados])
    assert len(cliente(config, sesion).consultar(["A1"])) == 1
    assert len(sesion.de("consulta")) == 2


def test_4xx_no_reintenta(config):
    sesion = SesionFalsa(consultas=[respuesta(400, {"message": "x"})])
    with pytest.raises(ErrorApi, match="HTTP 400"):
        cliente(config, sesion).consultar(["A1"])
    assert len(sesion.de("consulta")) == 1


def test_error_explicito_no_se_convierte_en_no_encontrado(config):
    sesion = SesionFalsa(consultas=[respuesta(200, {"data": [], "message": "cli_id invalido"})])
    with pytest.raises(ErrorApi, match="cli_id invalido"):
        cliente(config, sesion).consultar(["A1"])


def test_forma_inesperada_y_no_json(config):
    with pytest.raises(RespuestaInesperada):
        cliente(config, SesionFalsa(consultas=[respuesta(200, {"otra": 1})])).consultar(["A1"])
    with pytest.raises(RespuestaInesperada):
        cliente(config, SesionFalsa(consultas=[respuesta(200, texto="<html>")])).consultar(["A1"])


def test_login_rechazado_sin_filtrar_secretos(config):
    sesion = SesionFalsa(login=[respuesta(401, {})])
    with pytest.raises(ErrorApi) as info:
        cliente(config, sesion).consultar(["A1"])
    assert "credenciales" in str(info.value)
    assert "contrasena-ficticia" not in str(info.value)
    with pytest.raises(ErrorApi, match="access_token"):
        cliente(config, SesionFalsa(login=[respuesta(200, {"data": {}})])).consultar(["A1"])


def test_presupuesto_de_tiempo(config):
    reloj = iter([0, 0, 1000, 1000, 1000])
    c = ClienteTdx(replace(config.api, presupuesto_segundos=30), sesion=SesionFalsa(), reloj=lambda: next(reloj))
    with pytest.raises(ErrorApi, match="tiempo maximo"):
        c.consultar(["A1"])