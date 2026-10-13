# Contrato de ingreso SMS firmado (GR1)

Este canal agrega una entrada firmada al backend; no cambia la API web
existente. Los endpoints están bajo `/api/v1`.

## Preparación

1. El usuario solicita y verifica por OTP su número E.164:
   - `POST /telefonos/solicitar-otp`
   - `POST /telefonos/verificar-otp`
2. Con el teléfono verificado registra el ID del dispositivo:
   - `POST /dispositivos/registrar`
   - El secreto de 32 bytes se devuelve una sola vez, codificado Base64 URL-safe
     sin padding. Se debe guardar en Android Keystore.
3. El dispositivo usa ese secreto para firmar el mensaje de abajo. Se puede
   revocar mediante `POST /dispositivos/{device_id}/revocar`.

OTP y registro/revocación requieren JWT. La tabla almacena el hash del OTP y
el secreto de dispositivo cifrado, nunca el OTP o secreto en claro.
Aplica `database/migrations/20261010_signed_sms_channel.sql` antes de arrancar
una base existente: `Base.metadata.create_all` no agrega columnas a tablas
previas.

## Mensaje de dispositivo

El cuerpo del SMS es ASCII, una línea, máximo 160 bytes:

```text
GR1|<id>|<tipo>|<lat>|<lng>|<prec>|<edad>|<ts>|<grav>|<firma>
```

| Campo | Regla |
|---|---|
| `GR1` | Versión literal. |
| `id` | 10 caracteres Base32 RFC 4648 (`A-Z`, `2-7`). Es el `client_alert_id`; U y C reutilizan el ID original. |
| `tipo` | `A` automático sin respuesta, `M` manual, `C` cancelación, `U` actualización de ubicación. |
| `lat`, `lng` | Decimal con exactamente 5 cifras fraccionarias; rango WGS84. |
| `prec` | Precisión GPS en metros, entero entre 0 y 100000. |
| `edad` | Antigüedad de la lectura GPS en segundos, entero entre 0 y 31536000. |
| `ts` | Epoch UTC en segundos al disparar/emitir el mensaje. Se acepta dentro de la ventana configurada, por defecto ±86400 s. |
| `grav` | Entero 1-5. |
| `firma` | Primeros 8 caracteres Base32 sin `=` de HMAC-SHA256. |

### Canonicalización y HMAC

Antes de firmar, se quitan espacios alrededor de los campos, se eliminan CR/LF
y se convierten los campos a mayúsculas. La entrada al HMAC es ASCII y termina
en `grav`; no incluye el último separador `|` ni la firma. El secreto Base64
URL-safe se decodifica a los 32 bytes de clave HMAC. La firma se compara en
tiempo constante.

Ejemplo de mensaje de alerta:

```text
GR1|ABCDEFGHJK|A|-12.04640|-77.04280|5|3|1791500000|4|TRGS6IS7
```

Vector criptográfico conocido:

```text
Secreto (hex; convertir directamente a 32 bytes):
000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f

Texto firmado:
GR1|ABCDEFGHJK|A|-12.04640|-77.04280|5|3|1791500000|4

Firma esperada:
TRGS6IS7
```

El vector valida canonicalización y HMAC, no la ventana temporal; su timestamp
fijo puede estar vencido al probarlo.

### Significado persistido

- `A`: usa `TipoEmergencia.SISMO_INERCIAL`,
  `OrigenAlerta.AUTOMATICO_INERCIA` y
  `EstadoConfirmacion.EXPIRADO_INCONSCIENTE`.
- `M`: usa `TipoEmergencia.SISMO_INERCIAL`, `OrigenAlerta.MANUAL` y
  `EstadoConfirmacion.CONFIRMADO`.
- `U`: modifica coordenadas, precisión y edad de la misma alerta si continúa
  abierta.
- `C`: cancela una alerta aún no recibida, pone
  `EstadoConfirmacion.CANCELADO_USUARIO` y registra la transición en el
  historial append-only.

`client_alert_id` acepta el UUID existente de la API o el identificador GR1 de
10 caracteres. Si API y SMS reintentan el mismo ID y los campos de alerta
coinciden, la restricción única y la transacción existentes conservan una sola
alerta. El primer ingreso persistido fija `canal_entrada` (`API` o `SMS`);
un duplicado no reemplaza evidencia ni genera otra entrada outbox.

La vista institucional `/alertas/activas/` conserva su aislamiento: solo
muestra alertas asignadas a la institución autenticada. Una alerta que entra
por SMS se asigna igual que una de la API: a las instituciones activas cuya
cobertura validada por el propietario contiene el punto. Un SMS tipo `U` que
mueve la alerta dentro de otra cobertura agrega esa institución; las
asignaciones previas se conservan. Sin cobertura que la contenga, la alerta
queda persistida y visible para el propietario en *Alertas sin institución
asignada*; no se inventa una institución.

## Webhook del proveedor

`POST /sms/entrante` no acepta JWT: exige la firma del proveedor antes de
procesar el remitente o el SMS de dispositivo.

- `SMS_PROVIDER=console` (desarrollo/tests): configura `SMS_WEBHOOK_SECRET`.
  `SMS_SIGNATURE_HEADER` elige la cabecera (por defecto `X-SMS-Signature`) y
  el valor es `sha256=<hex HMAC-SHA256 del cuerpo HTTP sin modificar>`.
- `SMS_PROVIDER=twilio`: define `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` y
  `TWILIO_FROM_NUMBER`. El webhook verifica `X-Twilio-Signature` usando la URL
  pública y parámetros form-urlencoded según el esquema Twilio; acepta
  `From`/`Body` además de `remitente`/`texto`. Si el servicio está detrás de un
  proxy TLS, configura `SMS_WEBHOOK_PUBLIC_URL` exactamente con la URL pública
  registrada en Twilio.

En modo console no se entrega ningún SMS real. La ruta valida la firma del
proveedor, verifica que el remitente esté activo y verificado, comprueba la
firma del dispositivo y la ventana temporal, y finalmente registra la alerta.
Mensajes mal formados de teléfonos verificados quedan como `SMS_ILEGIBLE`;
otros descartes y contadores se consultan solo con token de propietario
rotado mediante `GET /sms/descartados`.

La respuesta a una alerta válida solicita el texto
`Recibimos tu alerta. Si estás en peligro llama al 105/116/106.` No afirma
recepción institucional. Twilio `queued` significa aceptado por el proveedor,
no entregado al teléfono; console no confirma envío.

## Variables de entorno

```text
SMS_PROVIDER=console
SMS_SIGNATURE_HEADER=X-SMS-Signature
SMS_WEBHOOK_PUBLIC_URL=
SMS_WEBHOOK_SECRET=<secreto aleatorio del webhook local>
SMS_OTP_PEPPER=<secreto aleatorio para hash OTP>
SMS_DEVICE_ENCRYPTION_KEY=<clave Fernet URL-safe de 32 bytes>
SMS_CONSOLE_PRINT_MESSAGES=false
SMS_TIMESTAMP_WINDOW_SECONDS=86400
SMS_OUTBOUND_LIMIT_COUNT=5
SMS_OUTBOUND_LIMIT_WINDOW_SECONDS=3600
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

No subas los valores reales al repositorio. Una clave Fernet se puede generar
localmente con `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
La rotación de `SMS_DEVICE_ENCRYPTION_KEY` requiere una migración operativa
que vuelva a cifrar los secretos antes de retirar la clave anterior.

## Verificar un teléfono sin proveedor (solo desarrollo)

Con `SMS_PROVIDER=console` no se entrega ningún SMS, así que el OTP no puede
llegar al teléfono y `POST /telefonos/solicitar-otp` responde 503. Para probar
el flujo completo en una máquina de desarrollo, define
`SMS_CONSOLE_PRINT_MESSAGES=true`: el texto que se habría enviado (incluido el
código OTP) se imprime en la terminal donde corre el backend y la solicitud
responde 200. Esta opción nunca debe activarse en un servidor real: quien lea
la terminal podría verificar cualquier número.

El recorrido completo (OTP, registro del dispositivo, SMS tipo A, U y C, y su
aparición en la bandeja institucional) está automatizado en
`backend/tests/test_postgis_integracion.py`.

## Simulador local

Con el backend arriba y un teléfono/dispositivo de prueba ya verificados,
configura `SMS_PROVIDER=console`, `SMS_WEBHOOK_SECRET`,
`GEORESCUE_SMS_SENDER` y `GEORESCUE_DEVICE_SECRET_B64`; después ejecuta desde
la raíz:

```powershell
.\backend\venv\Scripts\python.exe .\scripts\simular_sms.py --lat -12.04640 --lng -77.04280
```

El script firma el SMS y el cuerpo del webhook local. No contacta Twilio ni
envía SMS a una red telefónica.
