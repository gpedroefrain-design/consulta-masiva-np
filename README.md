# consulta-masiva-np

Aplicacion web sencilla (Python + Flask) para la **consulta masiva de numeros de parte (NP)**:
se sube un Excel `.xlsx` y se descarga un CSV con el resultado de la API de consulta masiva.
La consulta se hace **solo desde el servidor**; el navegador nunca recibe credenciales, tokens ni `cli_id`.

> Estado: primera version para uso local / piloto. **No hay despliegue publicado.**
> GitHub solo aloja el codigo; no ejecuta aplicaciones Python. Publicarla requiere un servidor
> (por ejemplo, Azure App Service o una VM interna) con **HTTPS**, autorizado por TI/seguridad.

## Formato de entrada

- Archivo `.xlsx` (no `.xls`, `.xlsm` ni `.csv`).
- Se usa la hoja `CONSULTA` si existe; si no, la hoja activa.
- La **primera fila** debe contener un encabezado `NUMERO_PARTE`, `NUMEROPARTE` o `NP`
  (sin distinguir mayusculas/espacios; si hay varios, prioridad en ese orden).
- Celdas vacias se omiten; duplicados (sin distinguir mayusculas) se consultan una sola vez,
  conservando la primera aparicion y el orden del archivo.
- Ceros a la izquierda: se conservan si la celda es **Texto**. Si Excel guardo el valor como numero,
  el cero ya no existe en el archivo y no se puede recuperar.

## Salida CSV

Codificacion `utf-8-sig` (con BOM, se abre bien en Excel). Una fila por NP unico, en el orden de entrada,
con estas columnas exactas:

```
numeroParteEnviado,encontrado,numeroParte,numeroParteInterno,fraccion,descripcionFactura,descripcionPedimento,pais,unidadMedida,marca,modelo,tipoMercancia,sustentoNormativo,igiTasa,observaciones
```

- `encontrado` se considera verdadero con `1`, `true`, `si` o `sí`; en otro caso se escribe `0` y,
  si la API no envio `observaciones`, se agrega "La API no devolvio un registro para este numero.".
- Las respuestas se asocian por `numeroParteEnviado` o `numeroParte` (sin distinguir mayusculas).
- Campos adicionales de la API se ignoran.

### Compatibilidad con el proceso anterior y cambios intencionales

Se mantiene: encabezados aceptados, hoja preferida, limpieza de blancos, deduplicacion, lotes de 5000,
timeout 180 s, 3 intentos por lote con renovacion de token ante 401, extraccion de resultados desde
lista o claves `data/results/resultados/resultado/items/numeros/response`, mapeo y orden de columnas.

Cambios intencionales:

- **Sin columna UNSPSC** y sin dependencia de catalogos o rutas de red.
- Respuesta con **forma no reconocida**, JSON invalido o mensaje de error explicito de la API
  -> la consulta falla con un error claro (no se convierte en "no encontrado").
- Errores HTTP 4xx (excepto 401) no se reintentan; 429/5xx, timeouts y errores de conexion si.
- NP de mas de 100 caracteres o con caracteres de control -> error indicando la fila.
- Celdas que empiezan con `=`, `@`, tabulador, retorno, o `+`/`-` seguido de algo que no es un numero,
  se prefijan con `'` para evitar inyeccion de formulas en Excel. NP normales (`ABC-1`, `00123`, `-5`) no cambian.
- Procesamiento en memoria por solicitud: no se guardan archivos subidos ni CSV en disco.

## Limites (configurables)

| Variable | Defecto | Descripcion |
|---|---|---|
| `MAX_UPLOAD_MB` | 10 | Tamano maximo del archivo subido (1-50). |
| `MAX_FILAS_NP` | 50000 | Filas con NP permitidas (1-200000). |
| `TIEMPO_MAXIMO_SEGUNDOS` | 600 | Presupuesto total de la consulta (login + lotes + reintentos). |
| `MAX_CONSULTAS_SIMULTANEAS` | 2 | Consultas concurrentes; el resto recibe "intente mas tarde". |

Ademas el XLSX se valida como ZIP: maximo 2000 entradas, 200 MB descomprimidos y relacion de
compresion maxima 200:1. La consulta es sincrona: el proxy/servidor debe permitir respuestas tan largas
como `TIEMPO_MAXIMO_SEGUNDOS` (waitress se configura con ese valor + 60 s).

## Seguridad

- Acceso con **contrasena compartida** (`APP_ACCESS_PASSWORD`) y sesion firmada (`APP_SECRET_KEY`).
  Es **provisional** y **no reemplaza SSO** corporativo (p. ej. Microsoft Entra ID); se recomienda
  sustituirla antes de un uso amplio.
- La app **no arranca** si falta alguna variable obligatoria (falla cerrado).
- Proteccion CSRF (token por sesion + verificacion de `Origin`), cookies `HttpOnly`, `SameSite=Strict`
  y `Secure` (por defecto), limite de 5 intentos de acceso fallidos por IP cada 15 min, cabeceras CSP,
  `X-Frame-Options` y `no-store`.
- Sin trazas de error al usuario; los registros no incluyen tokens, credenciales ni contenido de archivos.

## Configuracion en Windows

Requisitos: Python 3.10+.

```powershell
cd C:\Users\<usuario>\source\repos\consulta-masiva-np
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env   # completar valores; para pruebas locales en http use APP_COOKIE_SECURE=false
```

Variables obligatorias: `APP_SECRET_KEY` (>= 32 caracteres), `APP_ACCESS_PASSWORD` (>= 12),
`TDX_USERNAME`, `TDX_PASSWORD`, `TDX_CLI_ID`. Opcionales: `TDX_LOGIN_URL`, `TDX_QUERY_URL` (solo `https://`),
limites, `HOST` (127.0.0.1) y `PORT` (8000). El archivo `.env` esta en `.gitignore`; **nunca lo suba**.
Las variables del entorno del sistema tienen prioridad sobre `.env`.

## Ejecutar localmente

```powershell
.\.venv\Scripts\python.exe run.py
# abrir http://127.0.0.1:8000
```

## Pruebas

Las pruebas usan respuestas simuladas; **no llaman a la API real**.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## Despliegue (pendiente)

Pendiente de autorizacion. Requisitos minimos: HTTPS obligatorio, variables configuradas como secretos del
servidor (no en el repositorio), timeout del proxy >= `TIEMPO_MAXIMO_SEGUNDOS`, y preferentemente SSO.