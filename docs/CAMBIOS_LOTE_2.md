# Cambios del lote 2

Base: el lote 1 ya aplicado (`docs/CAMBIOS_LOTE_1.md`). La carpeta `android/`
no se tocó. Este lote reúne todo lo posterior al lote 1.

## Cómo aplicarlo

1. Descomprimir el zip en la raíz del proyecto, reemplazando archivos.
2. `python scripts/preparar_bd.py` (crea la tabla del directorio y dos columnas).
3. `cd backend` y `python -m pytest tests -q` -> `117 passed, 1 skipped`.
   Con PostGIS (`set GEORESCUE_TEST_POSTGIS=1`) -> `135 passed`.
4. Arrancar el backend, entrar como propietario y, en "Directorio de
   emergencia", cargar los dos archivos de `database/directorio/cajamarca/`:

   | Archivo | Fuente a escribir | Fecha |
   |---|---|---|
   | `directorio_cajamarca_comisarias.csv` | Prontuario telefónico de las comisarías del Frente Policial Cajamarca (PNP, gob.pe) | 17/03/2025 |
   | `directorio_cajamarca_salud.csv` | RENIPRESS - SUSALUD, archivo IPRESS.csv de Datos Abiertos | 10/10/2026 |

   En "Tipo de las filas" se deja "El archivo trae la columna tipo".
5. Para que las fotos lleguen por correo, configurar `SMTP_*` en `.env`
   (ver README, sección "Correo saliente").

## Números de emergencia cercanos

- Tabla `directorio_emergencia` (migraciones `20261012` y `20261013`).
- `GET /directorio/emergencia`: directorio público con `version`. No recibe la
  ubicación de nadie; el punto más cercano se calcula en el dispositivo y
  funciona con la copia guardada cuando no hay conexión.
- Panel de propietarios -> "Directorio de emergencia": carga por CSV (también
  el que guarda Excel en español), resumen, búsqueda, corrección de teléfono
  con fuente y fecha, y ocultar entradas.
- Pantalla del ciudadano -> "Cerca de ti", debajo de 105/116/106: comisaría,
  bomberos y salud más cercanos, con distancia, botón de llamada y fecha de
  verificación. Si el más cercano no tiene teléfono, agrega el más cercano que
  sí lo tenga. Indica cuándo la ubicación es aproximada.
- Datos reales del departamento de Cajamarca: 114 comisarías y 135
  establecimientos de salud, con `INFORME.txt` y el script que los genera
  (`scripts/armar_directorio_cajamarca.py`). Sus limitaciones están en
  `docs/DIRECTORIO_EMERGENCIA.md`; conviene leerlas antes de mostrarlos.

## Foto de evidencia al correo

- Con un correo de seguridad registrado, la cámara frontal toma una foto y el
  servidor la envía a ese correo con las coordenadas y un enlace al mapa cuando
  el usuario: envía un SOS, activa el pánico silencioso, toca un número de
  emergencia (105, 116, 106 o los de "Cerca de ti") o usa "Apagar sistema".
- La foto se toma en paralelo: no retrasa la alerta ni la llamada. Si la cámara
  falla, la alerta sale igual y el fallo queda en la bitácora.
- Los simulacros no toman foto ni envían correo.
- **Bloqueo del correo:** desde una alerta real (por la web, por SMS o pánico)
  o una evidencia, el correo guardado no se puede cambiar ni borrar durante
  `SECURITY_EMAIL_LOCK_HOURS` (24 por defecto). El servidor responde 423. Si no
  había ningún correo, sí se puede registrar uno.
- Al guardar el correo se pide el permiso de cámara, para que en una
  emergencia no aparezca ninguna pregunta.
- `tipo_evento` ahora es uno de `ANTI_THEFT`, `SOS`, `PANICO`,
  `LLAMADA_EMERGENCIA`; el asunto del correo dice qué lo provocó.
- Límite: 10 evidencias por hora y por cuenta. Migración `20261014`.

## Qué falta

- El envío real de correo no se probó: requiere configurar SMTP.
- En un celular, al tocar un número se abre el marcador y el navegador pasa a
  segundo plano; la foto puede no llegar a tomarse. En la app Android nativa
  esto se resuelve de otra forma.
- La app Android todavía no usa ni el directorio ni la evidencia.
- Coordenadas exactas de las comisarías de la ciudad de Cajamarca.
