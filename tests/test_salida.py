import csv
import io

from consulta_np.salida import COLUMNAS_SALIDA, construir_filas, generar_csv, neutralizar_formula

ESPERADAS = (
    "numeroParteEnviado,encontrado,numeroParte,numeroParteInterno,fraccion,descripcionFactura,"
    "descripcionPedimento,pais,unidadMedida,marca,modelo,tipoMercancia,sustentoNormativo,igiTasa,observaciones"
)


def test_columnas_exactas_sin_unspsc():
    assert ",".join(COLUMNAS_SALIDA) == ESPERADAS
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


def test_csv_bom_orden_y_formulas():
    filas = [{"numeroParteEnviado": "=CMD()", "encontrado": 1, "UNSPSC": "9", "marca": "@x", "modelo": "-123",
              "observaciones": None, "numeroParte": "00123"}]
    datos = generar_csv(filas)
    assert datos.startswith(b"\xef\xbb\xbf")
    lector = list(csv.reader(io.StringIO(datos.decode("utf-8-sig"))))
    assert ",".join(lector[0]) == ESPERADAS
    fila = dict(zip(lector[0], lector[1]))
    assert fila["numeroParteEnviado"] == "\x27=CMD()"
    assert fila["marca"] == "\x27@x"
    assert fila["modelo"] == "-123"
    assert fila["numeroParte"] == "00123"
    assert fila["observaciones"] == ""


def test_neutralizar_no_altera_np_normales():
    for np in ("ABC-123", "00123", "+5", "-1.5", "A=B", "12/34"):
        assert neutralizar_formula(np) == np
    for peligroso in ("+A1", "-2+3", "=1", "\t=1"):
        assert neutralizar_formula(peligroso).startswith("\x27")