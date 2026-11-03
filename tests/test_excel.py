import io
import zipfile

import pytest

from consulta_np.excel import ErrorEntrada, LimitesEntrada, leer_numeros_excel
from conftest import xlsx


def test_encabezados_aceptados_sin_distinguir_mayusculas():
    for encabezado in ("NP", " numero_parte ", "NumeroParte"):
        r = leer_numeros_excel(xlsx([["OTRA", encabezado], ["x", "A1"]]))
        assert r.numeros == ["A1"]


def test_prioridad_de_columna_numero_parte_sobre_np():
    r = leer_numeros_excel(xlsx([["NP", "NUMERO_PARTE"], ["mal", "bien"]]))
    assert r.numeros == ["bien"]


def test_blancos_duplicados_y_ceros_a_la_izquierda():
    r = leer_numeros_excel(xlsx([["NP"], ["00123"], [None], ["  "], ["abc"], ["ABC"], [" 00123 "], [456], ["B-1"]]))
    assert r.numeros == ["00123", "abc", "456", "B-1"]
    assert r.filas_con_np == 6
    assert r.duplicados == 2


def test_prefiere_hoja_consulta():
    r = leer_numeros_excel(xlsx([["NP"], ["DE-CONSULTA"]], extra_hoja=True))
    assert r.numeros == ["DE-CONSULTA"]


def test_falta_encabezado():
    with pytest.raises(ErrorEntrada, match="NUMERO_PARTE"):
        leer_numeros_excel(xlsx([["CODIGO"], ["A1"]]))


def test_archivo_vacio_o_sin_np():
    with pytest.raises(ErrorEntrada):
        leer_numeros_excel(xlsx([]))
    with pytest.raises(ErrorEntrada, match="no contiene"):
        leer_numeros_excel(xlsx([["NP"], [None]]))


def test_archivo_no_xlsx():
    with pytest.raises(ErrorEntrada, match="firma"):
        leer_numeros_excel(b"NP\nA1\n")


def test_zip_sin_workbook():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("hola.txt", "x")
    with pytest.raises(ErrorEntrada, match="workbook"):
        leer_numeros_excel(buffer.getvalue())


def test_zip_bomba_rechazado():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", "<x/>")
        z.writestr("xl/relleno.xml", "0" * 5_000_000)
    with pytest.raises(ErrorEntrada, match="compresion"):
        leer_numeros_excel(buffer.getvalue())
    with pytest.raises(ErrorEntrada, match="descomprimido"):
        leer_numeros_excel(buffer.getvalue(), LimitesEntrada(max_descomprimido_bytes=1000, max_ratio_compresion=10**9))


def test_limite_de_filas():
    with pytest.raises(ErrorEntrada, match="limite"):
        leer_numeros_excel(xlsx([["NP"], ["A"], ["B"], ["C"]]), LimitesEntrada(max_filas_np=2))


def test_np_invalidos():
    with pytest.raises(ErrorEntrada, match="fila 2"):
        leer_numeros_excel(xlsx([["NP"], ["X" * 101]]))