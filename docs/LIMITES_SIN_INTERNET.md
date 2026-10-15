# Límites y permisos de la protección Android

## Límites de entrega

- Sin cobertura celular y sin otros teléfonos cercanos que ejecuten una futura
  versión compatible, no se puede enviar el SMS ni retransmitir la alerta. La
  retransmisión Nearby Connections aún no está implementada.
- Si el teléfono se apaga, se queda sin batería, se destruye o el sistema
  fuerza la detención de la app antes del envío, la alerta no puede salir.
- Durante un sismo la red celular puede saturarse. Un SMS aceptado por el
  teléfono no demuestra que llegó al destinatario; el estado de entrega solo
  cambia cuando Android informa el callback de entrega.
- `SEND_SMS` está restringido por las políticas de Google Play. El piloto de
  envío directo está previsto para instalación de APK, sujeto a permisos y a
  las políticas vigentes.
- iOS no permite que una app envíe SMS automáticamente sin intervención del
  usuario. Este flujo automático es solo para Android.
- Los umbrales del acelerómetro son iniciales, no están certificados y deben
  calibrarse en campo para distintos dispositivos. No se garantiza la detección
  de todo sismo ni la ausencia de falsos positivos.
- La ubicación se solicita solo al dispararse una alerta. Si no hay lectura
  nueva en cinco segundos, se intenta utilizar la última conocida con su edad
  y precisión. Si Android no entrega ninguna ubicación, no se inventan
  coordenadas y el SMS firmado espera un dato válido; el envío API puede
  persistir sin coordenadas.
- Un callback HTTP de éxito solo confirma recepción por el servidor; no
  confirma recepción o atención institucional. El SMS `sentIntent` confirma
  aceptación por la red desde el dispositivo, no entrega al teléfono destino.
- La aparición en `/alertas/activas/` depende de que el backend ya tenga una
  institución activa con cobertura válida para esas coordenadas; Android no
  altera ni reemplaza la asignación institucional del servidor.
- Un token API expirado mantiene el trabajo de API en reintentos independientes
  hasta que el usuario vuelva a iniciar sesión. No detiene los trabajos SMS.
- "Estoy bien" guarda la cancelación local, solicita el cambio de estado al
  servidor si la API ya asignó un ID y envía GR1 tipo C cuando un SMS firmado
  anterior fue aceptado por la red. Si el servidor ya recibió o cerró la alerta,
  puede rechazar el cambio; la pantalla no lo presenta como confirmado.
- El número SMS de destino de la plataforma debe introducirse en ajustes; no
  está incluido en la aplicación.

## Permisos Android solicitados

| Permiso | Uso en la aplicación |
|---|---|
| `ACCESS_FINE_LOCATION` | Obtener coordenadas precisas después de una alerta sísmica; no se consulta durante la vigilancia en reposo. |
| `ACCESS_BACKGROUND_LOCATION` | Permitir obtener la ubicación cuando la cuenta regresiva vence con la pantalla bloqueada y la app en segundo plano. Si falta, la pantalla de estado avisa que no habrá GPS en segundo plano. |
| `FOREGROUND_SERVICE_LOCATION` | Autorizar el tipo `location` del servicio visible que inicia el muestreo GPS al dispararse una alerta en segundo plano. |
| `SEND_SMS` | Enviar el mensaje firmado GR1 a la plataforma y el mensaje legible a los contactos que dieron consentimiento. |
| `INTERNET` | Iniciar sesión, solicitar/verificar OTP, registrar el dispositivo y enviar/reintentar la alerta a la API. |
| `ACCESS_NETWORK_STATE` | Permitir que los trabajos de API esperen conectividad y reintenten cuando vuelva la red. |

La API exige HTTPS en builds release. Solo el source set debug permite HTTP
para pruebas contra un backend local; esa excepción no se incluye en release.

La ubicación en segundo plano, SMS y notificaciones se solicitan durante la
configuración. El permiso de batería sin restricciones se habilita desde los
ajustes del sistema; sin él la pantalla no muestra la protección como lista.
Android y cada fabricante pueden suspender procesos o restringir el acceso aun
cuando los permisos aparezcan concedidos.

Los secretos de firma y el token API se cifran con una clave AES de Android
Keystore. El secreto de dispositivo solo se solicita una vez al endpoint de
registro y no se escribe en logs ni en preferencias sin cifrar. Los contactos,
el número de plataforma y la cola de alertas permanecen en Room en el teléfono.

## Validación pendiente en dispositivos reales

No se ha podido compilar ni ejecutar el proyecto Android en el entorno de
desarrollo: no hay Gradle ni Gradle Wrapper en `android/`. Antes del piloto se
debe probar con Android Studio y teléfonos reales la pantalla bloqueada,
permisos de ubicación en segundo plano, GPS rápido y última ubicación, callbacks
SMS enviado/entregado, modo avión con radio celular activada, reinicio del
teléfono, batería restringida, pérdida de red, token vencido, cancelación GR1 C
y actualización GR1 U. El requisito de menos de 20 segundos debe medirse en
cada modelo y red del piloto; no se puede prometer por planificación de Android
ni por la cola del operador.
