# Pendientes antes de operación real

Este documento registra dependencias que requieren validación institucional,
legal u operativa. No se deben reemplazar por datos de demostración ni tratar
como acuerdos confirmados.

## Validación oficial y legal

- Verificar con fuentes oficiales peruanas los números de emergencia que se
  mostrarán en la pantalla SOS (PNP 105, Bomberos 116 y SAMU 106), registrar
  fuente y fecha de verificación, y obtener revisión legal de su publicación.
- Obtener revisión legal del consentimiento, tratamiento de ubicación,
  conservación de alertas e historial, y protocolo de acceso a datos de
  familiares e instituciones.
- Definir convenios y responsabilidades de respuesta con las instituciones
  que decidan inscribirse. La plataforma no implica que una institución haya
  recibido, aceptado o atendido una alerta.

- El bloque «Cerca de ti» muestra números locales desde un directorio que
  carga el propietario (ver `docs/DIRECTORIO_EMERGENCIA.md`). El repositorio
  no trae datos: falta elegir las fuentes oficiales, verificarlas, registrar la
  fecha y obtener revisión legal antes de publicarlos.

## Cobertura y operación institucional

- La cobertura geográfica ya tiene mecanismo técnico: el propietario registra
  por institución un centro, un radio y la evidencia consultada, y solo
  entonces se le asignan alertas. Sigue pendiente definir qué documento se
  acepta como evidencia y quién la revisa; hoy es un texto libre sin
  validación automática. Un círculo es una aproximación: una jurisdicción real
  puede no ser circular.
- Acordar responsables, horarios de operación, protocolo de confirmación,
  escalamiento y revisión de fallos con cada institución participante.
- Validar que los datos de cada institución inscrita, aprobada y activa sean
  correctos y estén vigentes. No configurar una institución predeterminada.

## Dependencias técnicas externas

- No hay proveedores externos de notificación ni de rutas configurados. El
  fallback no despacha mensajes, no informa cobertura, y no calcula rutas,
  distancias ni tiempos estimados.
- Cualquier futura implementación de gateway requiere contrato e
  implementación por interfaz, configuración mediante variables de entorno,
  secretos fuera del código, pruebas de fallos y confirmaciones respaldadas
  por evidencia del proveedor.
- La operación del outbox requiere definir y probar su consumidor, política de
  reintentos y revisión de fallos antes de afirmar que los eventos pendientes
  se procesan automáticamente.

## Pendientes técnicos conocidos

- El correo de seguridad se guarda sin verificar que pertenezca al usuario. El
  envío está limitado a 10 evidencias por hora y por cuenta, pero falta un paso
  de confirmación por correo antes de operar.
- El correo de seguridad se puede cambiar libremente mientras no haya una
  alerta o evidencia en las últimas 24 horas. Quien tenga el dispositivo con la
  sesión abierta podría cambiarlo antes de que se active nada; pedir la
  contraseña para cambiarlo cerraría ese caso.
- La foto de evidencia capta a quien esté frente a la cámara, que puede ser un
  tercero. Falta la revisión legal de esa captura y de su conservación, y
  definir cuánto tiempo se guardan las fotos.
- En el navegador de un celular, la foto al tocar un número de emergencia puede
  no tomarse porque el marcador pasa al frente.
- El aviso en tiempo real a la bandeja institucional vive en la memoria de un
  solo proceso: con más de un worker de uvicorn hay que refrescar la bandeja o
  mover el aviso a un canal compartido.
- Una alerta que la institución ya cerró deja de listarse en su bandeja; no hay
  todavía una vista de historial de alertas atendidas.
- El ciudadano no ve en su pantalla cuándo la institución confirma la
  recepción; solo ve en qué bandeja quedó al enviarla.
- Las pruebas contra PostGIS se ejecutan a pedido
  (`GEORESCUE_TEST_POSTGIS=1`); no hay integración continua que las corra.
- La entrega real de SMS con Twilio no se ha ejecutado: requiere una cuenta,
  un número y la URL pública del webhook.

Las alertas actualmente se persisten en la plataforma. Los buzones familiares
solo incluyen vínculos aceptados y no revocados; no se envía información a
sistemas externos.
