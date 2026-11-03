import io
import zipfile

from openpyxl import load_workbook

from consulta_np.salida import (
    COLUMNAS_SALIDA, HOJA_RESULTADOS, MARCA_TRUNCADO, MAX_CARACTERES_CELDA, construir_filas, generar_xlsx,
    parece_formula, valor_celda,
)
from conftest import leer_resultados

ESPERADAS = [
    "numeroParteEnviado", "encontrado", "numeroParte", "numeroParteInterno", "fraccion", "descripcionFactura",
    "descripcionPedimento", "pais", "unidadMedida", "marca", "modelo", "tipoMercancia", "sustentoNormativo",
    "igiTasa", "observaciones",
]


def test_columnas_exactas_sin_unspsc():
    assert COLUMNAS_SALIDA == ESPERADAS
    assert "UNSPSC" not in COLUMNAS_SALIDA


def test_mapeo_orden_y_no_encontrados():
    respuestas = [
        {"numeroParte": "b-2", "encontrado": "true", "fraccion": "1"},
        {"numeroParteEnviado": "A-1", "encontrado": "S\u00cd", "UNSPSC": "111"},
        {"numeroParteEnviado": "C-3", "encontrado": "no"},
    ]
    filas, enc, no = construir_filas(["a-1", "B-2", "C-3", "D-4"], respuestas)
    assert [f["numeroParteEnviado"] for f in filas] == ["A-1", "B-2", "C-3", "D-4"]
    assert (enc, no) == (2, 2)
    assert filas[2]["encontrado"] == 0 and "no devolvio" in filas[2]["observaciones"]
    assert filas[3] == {"numeroParteEnviado": "D-4", "encontrado": 0,
                        "observaciones": "La API no devolvio un registro para este numero."}


def test_valores_encontrado():
    for valor in (1, "1", True, "true", "Si", "s\u00ed"):
        _, enc, _ = construir_filas(["X"], [{"numeroParte": "X", "encontrado": valor}])
        assert enc == 1, valor


def test_xlsx_hoja_encabezado_y_orden():
    filas, _, _ = construir_filas(["A1", "00123", "b2"], [{"numeroParte": "a1", "encontrado": 1, "UNSPSC": "9"}])
    hoja, valores = leer_resultados(generar_xlsx(filas))
    assert hoja.title == HOJA_RESULTADOS
    assert valores[0] == ESPERADAS
    assert all(c.font.b for c in hoja[1])
    assert hoja.freeze_panes == "A2"
    assert [v[:3] for v in valores[1:]] == [["A1", "1", "a1"], ["00123", "0", None], ["b2", "0", None]]
    assert len(valores) == 4 and all(len(v) == len(ESPERADAS) for v in valores)
    assert "UNSPSC" not in str(valores) and "9" not in [c for v in valores[1:] for c in v]


def test_xlsx_texto_ceros_unicode_y_vacias():
    filas = [{"numeroParteEnviado": "00123", "encontrado": 1, "numeroParte": "0007", "fraccion": "01020304",
              "igiTasa": 5, "descripcionFactura": "Tuerca \u00f1and\u00fa \u4e2d\u6587 \u20ac \U0001F600",
              "observaciones": None, "marca": "", "modelo": True, "pais": 1.5}]
    hoja, valores = leer_resultados(generar_xlsx(filas))
    fila = dict(zip(valores[0], valores[1]))
    assert fila["numeroParteEnviado"] == "00123" and fila["numeroParte"] == "0007"
    assert fila["fraccion"] == "01020304"
    assert fila["descripcionFactura"] == "Tuerca \u00f1and\u00fa \u4e2d\u6587 \u20ac \U0001F600"
    assert (fila["encontrado"], fila["igiTasa"], fila["modelo"], fila["pais"]) == ("1", "5", "True", "1.5")
    assert fila["observaciones"] is None and fila["marca"] is None and fila["numeroParteInterno"] is None
    for celda in hoja[2]:
        assert celda.value is None or celda.data_type == "s", celda.coordinate


def test_xlsx_formulas_no_evaluables():
    peligrosos = ['=HYPERLINK("http://malo.example","clic")', "=1+1", "+A1", "-2+3", "@SUM(A1)", "\t=1"]
    filas = [{"numeroParteEnviado": v, "descripcionFactura": v, "encontrado": 0} for v in peligrosos]
    filas.append({"numeroParteEnviado": "-5", "marca": "+1.5", "modelo": "ABC-1", "encontrado": 0})
    contenido = generar_xlsx(filas)
    hoja, valores = leer_resultados(contenido)
    assert [v[0] for v in valores[1:]] == peligrosos + ["-5"]
    assert [v[5] for v in valores[1:-1]] == peligrosos
    for fila in hoja.iter_rows(min_row=2):
        for celda in fila:
            if celda.value is not None:
                assert celda.data_type == "s", celda.coordinate
    assert hoja["A2"].quotePrefix and hoja["F2"].quotePrefix and not hoja["J8"].quotePrefix
    calculado = load_workbook(io.BytesIO(contenido), data_only=True)[HOJA_RESULTADOS]
    assert calculado["A2"].value == peligrosos[0]
    xml = zipfile.ZipFile(io.BytesIO(contenido)).read("xl/worksheets/sheet1.xml")
    assert b"<f>" not in xml and b"<f " not in xml
    assert b"HYPERLINK" in xml and not xml.startswith(b"\xef\xbb\xbf")


def test_parece_formula_no_marca_np_normales():
    for np in ("ABC-123", "00123", "+5", "-1.5", "A=B", "12/34", ""):
        assert not parece_formula(np)
    for peligroso in ("+A1", "-2+3", "=1", "\t=1", "@x", "\r1"):
        assert parece_formula(peligroso)


def test_valor_celda_tipos_y_caracteres_invalidos():
    assert valor_celda(None) == ""
    assert valor_celda({"a": 1}) == "{'a': 1}" and valor_celda([1, "x"]) == "[1, 'x']"
    assert valor_celda("a\x00b\x1fc\td") == "a\ufffdb\ufffdc\td"
    largo = valor_celda("x" * (MAX_CARACTERES_CELDA + 10))
    assert len(largo) == MAX_CARACTERES_CELDA and largo.endswith(MARCA_TRUNCADO)
    _, valores = leer_resultados(generar_xlsx([{"numeroParteEnviado": "A\x01", "observaciones": {"k": ["v"]}}]))
    assert valores[1][0] == "A\ufffd" and valores[1][-1] == "{'k': ['v']}"
