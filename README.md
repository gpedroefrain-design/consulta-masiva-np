# consulta-masiva-np

Aplicacion web sencilla (Python + Flask) para la **consulta masiva de numeros de parte (NP)**:
se sube un Excel `.xlsx` y se descarga un Excel `.xlsx` con el resultado de la API de consulta masiva.
La consulta se hace **solo desde el servidor**; el navegador nunca recibe credenciales, tokens ni `cli_id`.

> Estado: primera version para uso local / piloto. **No hay despliegue publicado.**
> GitHub solo aloja el codigo; no ejecuta aplicaciones Python. El repositorio incluye la preparacion
> para **AWS Elastic Beanstalk** (ver [Despliegue en AWS Elastic Beanstalk](#despliegue-en-aws-elastic-beanstalk)),
> pero **no se ha creado ningun recurso en AWS**; publicarla requiere cuenta, **HTTPS** y autorizacion de TI/seguridad.

## Formato de entrada

- Archivo `.xlsx` (no `.xls`, `.xlsm` ni `.csv`).
- Se usa la hoja `CONSULTA` si existe; si no, la hoja activa.
- La **primera fila** debe contener un encabezado `NUMERO_PARTE`, `NUMEROPARTE` o `NP`
  (sin distinguir mayusculas/espacios; si hay varios, prioridad en ese orden).
- Celdas vacias se omiten; duplicados (sin distinguir mayusculas) se consultan una sola vez,
  conservando la primera aparicion y el orden del archivo.
- Ceros a la izquierda: se conservan si la celda es **Texto**. Si Excel guardo el valor como numero,
  el cero ya no existe en el archivo y no se puede recuperar.

### Layout (plantilla)

En la pantalla de carga, el enlace **Descargar layout** (`GET /layout`) descarga `layout_consulta_np.xlsx`,
generado en memoria: hoja `CONSULTA`, encabezado `NP` en la fila 1 y columna A con formato **Texto**.
La plantilla esta vacia (sin NP de ejemplo). Capture un NP por celda **desde la fila 2**. El formato Texto
ayuda a conservar ceros a la izquierda, pero el lector solo respeta lo que Excel guardo como texto: si pega
datos, use "Pegar valores" y verifique los ceros. La descarga usa el mismo acceso que la pagina
(sesion iniciada si `APP_REQUIRE_LOGIN=true`; solo loopback si es `false`).

En la pantalla, el bloque **Instrucciones** se puede contraer o expandir con clic, toque o teclado
(Enter/Espacio sobre el titulo); inicia expandido.

## Salida XLSX

El boton **RUN** envia el archivo y descarga `consulta_np_AAAAMMDD_HHMMSS.xlsx`
(`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`), generado en memoria con una hoja
`RESULTADOS`: fila 1 con los encabezados (en negrita, inmovilizada) y una fila por NP unico, en el orden de
entrada, con estas columnas exactas:

```
numeroParteEnviado,encontrado,numeroParte,numeroParteInterno,fraccion,descripcionFactura,descripcionPedimento,pais,unidadMedida,marca,modelo,tipoMercancia,sustentoNormativo,igiTasa,observaciones
```

- `encontrado` se considera verdadero con `1`, `true`, `si` o `sí`; en otro caso se escribe `0` y,
  si la API no envio `observaciones`, se agrega "La API no devolvio un registro para este numero.".
- Las respuestas se asocian por `numeroParteEnviado` o `numeroParte` (sin distinguir mayusculas).
- Campos adicionales de la API se ignoran.
- Todas las celdas con datos se guardan como **texto** (mismo texto que antes producia el CSV, por ejemplo
  `encontrado` = `1`/`0`), por lo que NP y codigos conservan ceros a la izquierda; valores ausentes quedan
  como celdas vacias. Se conservan acentos y caracteres Unicode.

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
- **Salida en XLSX** (hoja `RESULTADOS`) en lugar de CSV.
- Proteccion contra formulas: cada celda se escribe con tipo texto explicito, de modo que valores como
  `=HYPERLINK(...)`, `@x` o `+A1` se muestran tal cual y nunca se evaluan; no se agrega apostrofo visible.
  A las que parecen formula (empiezan con `=`, `@`, tabulador, retorno, o `+`/`-` seguido de algo que no es un
  numero) ademas se les marca "prefijo de texto" para que Excel no las convierta si se editan.
- Caracteres de control no permitidos por el formato XLSX se reemplazan por `U+FFFD` (�); textos de mas de
  32767 caracteres (limite de Excel) se recortan y terminan en `...[truncado]`.
- Procesamiento en memoria por solicitud: no se guardan archivos subidos ni resultados en disco.

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
- **Modo local sin contrasena (solo piloto en loopback)**: `APP_REQUIRE_LOGIN=false` desactiva la pantalla
  de acceso y el boton de cerrar sesion; `GET /` muestra directamente la carga del XLSX. Solo se permite con
  `HOST` de loopback (`127.0.0.1`, `::1` o `localhost`); con otro valor la app **no arranca**. Ademas rechaza
  (403) peticiones cuyo par TCP no sea loopback, salvo que se habilite el proxy local de confianza descrito
  abajo. Se mantienen CSRF, cookies, limites de carga/concurrencia y validaciones; `APP_SECRET_KEY` y las
  credenciales TDX siguen siendo obligatorias. Riesgo: cualquier usuario o proceso del mismo equipo puede
  consultar la API. El valor por defecto es `true` (con contrasena); valores distintos de true/false son error.
- `APP_TRUST_PROXY=true` solo se permite si `HOST` es loopback. Habilita confianza en **un** proxy local
  para obtener la IP del cliente desde `X-Forwarded-For`; configuralo unicamente cuando el backend no sea
  accesible desde internet y el proxy reemplace esa cabecera con la direccion TCP del cliente. No lo actives
  con cadenas de proxies ni con `X-Forwarded-For` controlado por el cliente.
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

Variables obligatorias: `APP_SECRET_KEY` (>= 32 caracteres), `APP_ACCESS_PASSWORD` (>= 12, solo si
`APP_REQUIRE_LOGIN=true`, que es el defecto), `TDX_USERNAME`, `TDX_PASSWORD`, `TDX_CLI_ID`. Opcionales:
`APP_REQUIRE_LOGIN` (`true`/`false`, ver Seguridad), `TDX_LOGIN_URL`, `TDX_QUERY_URL` (solo `https://`),
limites, `HOST` (127.0.0.1), `PORT` (8000) y `APP_TRUST_PROXY` (false; solo para un proxy local de confianza).
El archivo `.env` esta en `.gitignore`; **nunca lo suba**.
Las variables del entorno del sistema tienen prioridad sobre `.env`.

## Ejecutar localmente

```powershell
.\.venv\Scripts\python.exe run.py
# abrir http://127.0.0.1:8000
```

Si cambia `.env` (por ejemplo `APP_REQUIRE_LOGIN`), detenga el servidor con Ctrl+C y vuelva a ejecutarlo.

## Pruebas

Las pruebas usan respuestas simuladas; **no llaman a la API real**. Verifican, entre otros, el XLSX de
resultados (hoja, columnas y orden exactos sin UNSPSC, texto con ceros a la izquierda, formulas no evaluables),
el layout, CSRF, acceso con contrasena por defecto, modo local solo loopback y los artefactos de despliegue
en Elastic Beanstalk (configuracion sin secretos, timeouts coherentes, `.ebignore` y ZIP por lista blanca).

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## Despliegue piloto en EC2

La configuracion para el piloto de una sola instancia esta en `deploy/ec2/`. Esta preparada para Amazon Linux 2023,
Waitress bajo systemd, Nginx como proxy local y una IPv4 elastica. La aplicacion escucha solo en `127.0.0.1:8000`;
el grupo de seguridad no debe abrir el puerto 8000 ni SSH. Para administracion se requiere un perfil de instancia
con `AmazonSSMManagedInstanceCore` y acceso por Systems Manager. No se crea ALB, NAT Gateway, RDS ni base de datos.

El acceso publico usa HTTPS directamente sobre la IPv4 con un certificado IP de Let's Encrypt. Estos certificados
duran 160 horas; `certbot` se ejecuta dos veces al dia y recarga Nginx al renovar. El puerto 80 solo sirve el reto
ACME y redirige el resto a HTTPS. Debe mantenerse operativo el timer de renovacion: Certbot 5.4+ puede emitirlos,
pero la configuracion de Nginx se administra manualmente en estos archivos.

En una instancia nueva, con el codigo aprobado disponible en `/home/ec2-user/consulta-masiva-np`:

1. Asigne una IPv4 elastica y permita entrada publica solo en TCP 80 y 443. Mantenga el puerto 22 cerrado; habilite
   IMDSv2 y el perfil de instancia de Systems Manager. Use un volumen raiz gp3 cifrado de 8 GiB y modo CPU Standard.
2. Ejecute `sudo bash deploy/ec2/install.sh <IPv4-elastica>`. El script instala Nginx, Python 3.12 y Certbot 5.4+,
   copia solo `run.py`, `requirements.txt`, `consulta_np/` y `deploy/ec2/`, instala los servicios y deja Nginx en
   modo de validacion ACME. No copia `.env`, pruebas, `.git` ni la preparacion antigua de Elastic Beanstalk.
3. Cree el archivo de secretos de forma interactiva, nunca como argumento o user data:

   ```bash
   sudo install -o root -g root -m 600 /dev/null /etc/consulta-np/app.env
   sudoedit /etc/consulta-np/app.env
   ```

   Introduzca `APP_SECRET_KEY`, `APP_ACCESS_PASSWORD`, `TDX_USERNAME`, `TDX_PASSWORD` y `TDX_CLI_ID`.
   Genere valores nuevos para la clave de sesion y la contrasena de acceso. No copie el `.env` local.
4. Ejecute `sudo bash deploy/ec2/enable-https.sh <IPv4-elastica>`. El script solicita el certificado IP,
   instala la configuracion TLS, valida y recarga Nginx, habilita la renovacion automatica y arranca la app.
5. Compruebe `https://<IPv4-elastica>/salud` y el formulario de acceso desde fuera de EC2. La primera consulta
   real a TDX requiere autorizacion aparte.

`APP_TRUST_PROXY=true` solo se activa en el servicio systemd porque el backend queda ligado a loopback y Nginx
reemplaza `X-Forwarded-For` con la direccion TCP del cliente. No use esa opcion si cambia la topologia o agrega
otra capa de proxies. Esta preparacion no crea recursos por si misma; el aprovisionamiento requiere autorizacion
explicita y verificar el costo/cobertura en la cuenta antes de lanzar.

## Despliegue en AWS Elastic Beanstalk

Preparacion anterior para **Elastic Beanstalk, plataforma Python en Amazon Linux 2023** (entorno con balanceador).
**No se debe usar para el piloto EC2 descrito arriba**: requiere un ALB y tiene costos distintos.
Nada de esto crea recursos ni costos por si mismo: los pasos de abajo los ejecuta una persona autorizada
en su cuenta de AWS. No se ha verificado contra una cuenta real.

### Archivos de despliegue

| Archivo | Proposito |
|---|---|
| `Procfile` | `web: python run.py`: el mismo arranque con waitress que en local (sin gunicorn ni codigo extra). |
| `.ebextensions/01_consulta_np.config` | Opciones del entorno (JSON). Sin secretos ni ARNs. |
| `.platform/nginx/conf.d/consulta_np.conf` | Tamano maximo del cuerpo y timeouts de nginx (bloque `http`). |
| `.ebignore` | Exclusiones del paquete que crea la EB CLI. |
| `empaquetar_eb.py` | Genera el ZIP con lista blanca para subirlo por la consola. |

`.ebextensions/01_consulta_np.config` define:

- Variables no secretas: `HOST=0.0.0.0`, `PORT=8000` (puerto al que nginx de EB envia el trafico),
  `APP_REQUIRE_LOGIN=true`, `APP_COOKIE_SECURE=true`, `TIEMPO_MAXIMO_SEGUNDOS=600`, `MAX_UPLOAD_MB=10`.
  Con `HOST=0.0.0.0` la app **no arranca** si alguien pone `APP_REQUIRE_LOGIN=false` (el modo sin contrasena
  exige loopback), asi que no se puede publicar sin acceso por error. waitress queda detras de nginx; el
  puerto 8000 no se abre en el grupo de seguridad (EB solo permite el 80 desde el balanceador).
  **No** use `HOST=127.0.0.1` en EB: nginx conecta por loopback y anularia esa proteccion.
- `EnvironmentType=LoadBalanced`, `LoadBalancerType=application` (ALB, necesario para HTTPS con ACM).
- `MinSize=1`, `MaxSize=1` (ver Estado por instancia).
- Health check del ALB en `/salud` (HTTP 200, sin login, no expone datos).
- `IdleTimeout=720` del ALB.

Los valores puestos en la consola o con `eb create/eb setenv` tienen **prioridad** sobre `.ebextensions`, y la
consola/EB CLI pueden imponer su valor recomendado en opciones como el tipo de balanceador. Al crear el
entorno elija explicitamente **High availability / balanceador Application** y revise en
*Configuration* que los valores coincidan.

### Timeouts y tamano de carga (relacion fija)

La consulta es **sincrona**: el navegador espera la respuesta completa. Cadena actual:

| Capa | Valor | Regla |
|---|---|---|
| App: `TIEMPO_MAXIMO_SEGUNDOS` | 600 s | Presupuesto de la consulta (aproximado: el timeout de `requests` es por operacion). |
| waitress `channel_timeout` | 660 s | `TIEMPO_MAXIMO_SEGUNDOS + 60` (calculado en `run.py`). |
| nginx `proxy_read_timeout` / `proxy_send_timeout` | 660 s | `>= TIEMPO_MAXIMO_SEGUNDOS + 60`. |
| ALB `IdleTimeout` | 720 s | Mayor que nginx; maximo configurable en EB: 3600 s. |
| nginx `client_max_body_size` | 11 MB | `MAX_UPLOAD_MB` (10) + margen del multipart; la app sigue aplicando su limite de 10 MB. |

Por defecto nginx en EB acepta solo 1 MB y el ALB corta a los 60 s; por eso estos valores son obligatorios.
Si sube `TIEMPO_MAXIMO_SEGUNDOS` (max. 3600 en la app) o `MAX_UPLOAD_MB` (max. 50), actualice **los tres**
archivos manteniendo la regla (las pruebas lo verifican). Advertencias: con `TIEMPO_MAXIMO_SEGUNDOS` cercano a
3600 ya no cabe el margen bajo el maximo del ALB; proxies corporativos, VPN o el navegador pueden cortar
antes; no ponga CloudFront delante (su timeout de origen es mucho menor). Un despliegue o reinicio con una
sola instancia corta las consultas en curso y deja la app sin servicio unos minutos.

### Estado por instancia (por que `MaxSize=1`)

- La sesion es una cookie firmada (`APP_SECRET_KEY`): funcionaria con varias instancias si comparten la clave.
- Pero el limite de consultas simultaneas (`MAX_CONSULTAS_SIMULTANEAS`) y el bloqueo de intentos de login
  viven **en memoria del proceso**: con N instancias serian N veces mas consultas a TDX y N contadores.
- Para el piloto se fija **una instancia** (sin Redis ni servicios extra). Para escalar, primero mover ese
  estado a un almacen compartido.
- Detras de nginx/ALB la app ve como origen a nginx (`127.0.0.1`), por lo que el limite de 5 intentos
  fallidos cada 15 min es **global**, no por IP: protege contra fuerza bruta, pero alguien con la URL puede
  bloquear el login de todos 15 min. No se confia en `X-Forwarded-For` (falsificable si no se valida la cadena
  exacta de proxies). Mitigacion: restringir el origen en el grupo de seguridad del ALB (ver abajo).

### Requisitos previos (bloqueantes, fuera de este repositorio)

1. **Cuenta de AWS** y autorizacion de TI/seguridad y de presupuesto; **region** elegida (todo en la misma).
2. **Dominio** propio y acceso a su DNS, y **certificado de AWS Certificate Manager (ACM) en la misma region
   que el ALB**. La URL `*.elasticbeanstalk.com` es solo HTTP: **no** hay HTTPS automatico y, como la cookie es
   `Secure`, el login no funciona por HTTP (y la contrasena viajaria sin cifrar). No use la app sin HTTPS.
3. Confirmar con el proveedor de TDX si exige **lista blanca de IP de origen**. La salida a internet de EB no
   tiene IP fija por defecto (la IP publica de la instancia cambia al reemplazarse). Una IP estable requiere
   disenar red (p. ej. subred privada + NAT Gateway con Elastic IP, con costo adicional) y acordarlo con el
   proveedor. No se ha configurado ninguna.
4. Plataforma: *Python 3.x running on 64bit Amazon Linux 2023* (version >= 3.10, p. ej. 3.12 o 3.13) lanzada
   en o despues del 26-mar-2025 si usara secretos de Secrets Manager como variables.

### Costos y disponibilidad

Elastic Beanstalk no cobra por si mismo, pero **si** los recursos que crea, mientras existan: instancia **EC2**
(recomendada `t3.small`; `t3.micro` puede quedarse corta de memoria con archivos grandes), **Application Load
Balancer** (cargo por hora + LCU, aunque no haya trafico), volumen **EBS**, transferencia de datos, **Secrets
Manager** (por secreto/mes y llamadas), **CloudWatch Logs** si activa el envio de logs, y NAT/Elastic IP si se
necesitaran. Estime con la calculadora de precios de AWS antes de crear nada y configure una alerta de
presupuesto (AWS Budgets). **No hay garantia de capa gratuita** (depende de la cuenta y caduca; el ALB
normalmente genera cargo). Una sola instancia **no** ofrece alta disponibilidad: habra cortes en despliegues,
reinicios, fallas de la instancia o de la zona; no se garantiza 100 % de disponibilidad. Para dejar de pagar,
termine el entorno (*Terminate environment*) y borre secretos/certificados que no use.

### Secretos (nunca en el repositorio, la linea de comandos ni archivos versionados)

Variables secretas: `APP_SECRET_KEY` (>= 32), `APP_ACCESS_PASSWORD` (>= 12), `TDX_USERNAME`, `TDX_PASSWORD`,
`TDX_CLI_ID`. Se configuran con la integracion de EB con **AWS Secrets Manager**:

1. En la consola de Secrets Manager (misma region) cree un secreto *Other type of secret* y escriba los
   valores en el formulario (pares clave/valor con esos cinco nombres). Genere `APP_SECRET_KEY` y
   `APP_ACCESS_PASSWORD` nuevos y aleatorios para produccion; no reutilice los de su `.env` local.
2. Al rol de instancia de EB (por defecto `aws-elasticbeanstalk-ec2-role`) agreguele una politica que permita
   `secretsmanager:GetSecretValue` **solo** sobre el ARN de ese secreto (si el secreto usa una clave KMS propia,
   tambien `kms:Decrypt` sobre ella).
3. En EB: *Configuration > Updates, monitoring, and logging > Runtime environment variables > Add environment
   variable*, **Source = Secrets Manager**, nombre de la variable (p. ej. `TDX_PASSWORD`) y como valor el ARN
   del secreto seguido de `:NOMBRE_CLAVE` (extraccion de claves JSON, plataformas desde el 13-ene-2026). Con
   plataformas anteriores cree un secreto de texto plano por variable y use el ARN sin sufijo.
4. EB lee los secretos al arrancar la instancia: tras cambiarlos o rotarlos use *Restart app server(s)* o
   actualice el entorno.

No use la fuente *Plain text* para secretos (quedan visibles en la configuracion del entorno) ni
`eb setenv CLAVE=valor` (queda en el historial de la terminal). No agregue ARNs ni valores a
`.ebextensions` versionado.

### Paquete de codigo

El ZIP debe tener `Procfile`, `run.py`, `requirements.txt`, `consulta_np/`, `.ebextensions/` y `.platform/`
**en la raiz** (no una carpeta padre). **No comprima la carpeta completa** (incluiria `.env`, `.venv`, `.git`).
`.ebignore` solo afecta a la EB CLI; Git sigue usando `.gitignore`. El `.env` local nunca se modifica ni empaqueta.

Opcion A, consola (sin instalar nada): genere el ZIP por lista blanca y revise el manifiesto impreso.
Empaqueta el directorio de trabajo, incluidos cambios sin commit: confirme antes con `git status` que solo
contiene lo que quiere publicar.

```powershell
.\.venv\Scripts\python.exe empaquetar_eb.py   # crea dist\consulta-np-eb.zip (dist\ esta en .gitignore)
```

(`Compress-Archive` de Windows PowerShell 5.1 puede guardar rutas con `\` que fallan en Linux; por eso el script.)

Opcion B, EB CLI (opcional, no incluida ni instalada aqui): `eb deploy` respeta `.ebignore` y con ese archivo
presente **no usa git** e incluye archivos sin commit. Alternativa: `git archive --format=zip -o dist\eb.zip HEAD`
empaqueta solo lo **commiteado** (incluye `tests/`, inofensivo; nunca `.env`, que no esta versionado).

### Pasos en la consola (cuando haya autorizacion)

1. Elastic Beanstalk > *Create application* > entorno **Web server**, plataforma **Python** sobre **Amazon
   Linux 2023**, *Upload your code* con `dist\consulta-np-eb.zip`.
2. *Presets*: **High availability**; balanceador **Application**, publico; instancias min 1 / max 1; tipo de
   instancia (p. ej. `t3.small`). Rol de servicio y perfil de instancia: los que EB propone o los que defina TI.
3. Antes de exponerla: en el grupo de seguridad del ALB limite los puertos 80/443 a las IP de la empresa/VPN
   si es posible, y configure los secretos (seccion anterior). Si la app no arranca por falta de variables
   (falla cerrado), el health check `/salud` quedara rojo hasta configurarlas.
4. HTTPS: en ACM solicite el certificado del dominio (validacion DNS) en la **misma region**. En EB >
   *Configuration > Load balancer* agregue un listener **443 HTTPS** con ese certificado (destino: proceso
   `default`, puerto 80 HTTP). La redireccion **HTTP 80 -> HTTPS 443** se configura manualmente en la regla del
   listener 80 desde la consola de EC2 > Load Balancers (accion *Redirect to HTTPS*), o elimine el listener 80.
   Cree en su DNS un CNAME (o alias de Route 53) del dominio hacia la URL del entorno/ALB.
5. Verifique: `https://<dominio>/salud` responde `ok`; `https://<dominio>/` muestra el login; el login funciona
   (si responde "La sesion del formulario expiro" revise que nginx conserve la cabecera `Host`, ya que la app
   compara `Origin` con `Host`); una consulta pequena devuelve el XLSX. Los logs de la app estan en
   *Logs > Request logs* (`web.stdout.log`).

### Acceso: contrasena compartida (provisional)

En local se permite `APP_REQUIRE_LOGIN=false` porque solo escucha en loopback del propio equipo. En internet
cualquiera con la URL llega a la app, asi que en EB el acceso es **siempre** con `APP_ACCESS_PASSWORD`
+ HTTPS + cookie `Secure`. Es una medida provisional (una sola clave para todos, sin identificar usuarios
ni revocacion individual): cambiela si se filtra y reinicie. Para uso amplio se recomienda **SSO** corporativo
(p. ej. Microsoft Entra ID/OIDC, o autenticacion OIDC en el listener del ALB) y, opcionalmente, AWS WAF
(costo adicional).
