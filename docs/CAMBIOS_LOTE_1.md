# Cambios del lote 1

Base: commit `01c3ebe` ("cambios") de `main`. El backend y la web se
modificaron; la carpeta `android/` no se tocó.

## Cómo aplicarlo

1. `git pull` y comprobar con `git log -1 --oneline` que el último commit es
   `01c3ebe`. Si hay commits más nuevos que tocan los mismos archivos, no
   descomprimas encima: avisa para regenerar el lote sobre esa base.
2. Descomprimir el zip en la raíz del proyecto, reemplazando archivos.
3. `python scripts/preparar_bd.py` (crea o actualiza la base).
4. `cd backend` y `python -m pytest tests -q` → `101 passed, 1 skipped`.
5. Con PostGIS: `$env:GEORESCUE_TEST_POSTGIS = "1"` y de nuevo
   `python -m pytest tests -q` → `116 passed`.

## Qué cambia

### Base de datos
- `scripts/preparar_bd.py`: crea la base, activa PostGIS y aplica todas las
  migraciones en el orden correcto. Antes, en una base nueva, las migraciones
  `20261006` y `20261007` fallaban porque sus tablas aún no existían.
- El backend comprueba el esquema al arrancar; si faltan columnas aplica las
  migraciones y lo dice en la terminal.
- Migración nueva `20261011_cobertura_y_correo_seguridad.sql`.

### Asignación de alertas a instituciones
- El propietario registra por institución una cobertura (centro + radio +
  evidencia). Cada alerta nueva se asigna a las instituciones cuya cobertura
  contiene el punto; por eso ahora sí aparece en `/alertas/activas/`.
- Sin ubicación o fuera de cobertura: queda en "Alertas sin institución
  asignada" y el propietario la asigna a mano, con motivo auditado.
- Los simulacros no se asignan. El botón "Simular Sismo" de la web ahora envía
  `es_simulacro: true`.
- La bandeja institucional se refresca sola (WebSocket) y tiene botones para
  confirmar recepción y avanzar el estado.
- Endpoints nuevos: `GET /admin/institutions`,
  `PUT|DELETE /admin/institutions/{id}/coverage`,
  `GET /admin/alerts/unassigned`, `POST /admin/alerts/{id}/assign`.

### Red familiar
- La invitación se envía con el código del familiar (`codigo_invitado`), ya no
  con su nombre de usuario. Sigue requiriendo aceptación.
- `GET /familia/invitaciones/enviadas/` y lista de pendientes en pantalla.
- El error de carga muestra la causa real.

### Antirrobo (cámara y correo)
- `POST /security/anti-theft-alert` exige sesión. Antes cualquiera podía
  llamarlo sin token e indicar a qué correo enviar.
- El correo de destino es el que el usuario guarda (`PUT /security/contact`);
  ya no se usa `usuario@georescue.local` ni un correo por defecto.
- La respuesta dice si el correo salió o por qué no. Sin GPS no se inventa una
  ubicación. Máximo 5 evidencias por hora y por cuenta.
- El usuario puede ver sus evidencias (`GET /security/events`).
- Para que el correo salga hay que configurar `SMTP_*` en `.env`.

### SMS firmado
- `SMS_CONSOLE_PRINT_MESSAGES=true` (solo desarrollo) muestra el OTP en la
  terminal del backend. Sin esto, en modo `console` era imposible verificar un
  teléfono y por tanto probar el canal completo.
- El flujo OTP → dispositivo → SMS A/U/C → bandeja institucional está probado
  de punta a punta en `backend/tests/test_postgis_integracion.py`.

### Correcciones menores
- La bandeja institucional mostraba sin escapar el tipo de emergencia y el
  usuario, que vienen de la app del ciudadano (riesgo de inyección de HTML).
- La cola local de reintentos del SOS reenvía la alerta completa tal como se
  intentó enviar.

## Qué NO está validado
- Entrega real de SMS con Twilio (requiere cuenta y número).
- Envío real de correo (se probó con un servidor SMTP simulado).
- La app Android: no se compiló ni se modificó en este lote.
- Ver `docs/PENDIENTES.md`, sección "Pendientes técnicos conocidos".
