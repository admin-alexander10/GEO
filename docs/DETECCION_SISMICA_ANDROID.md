# Detección sísmica Android (experimental)

El módulo aislado `android/` implementa vigilancia del acelerómetro en primer
plano, filtrado paso-alto, STA/LTA, cuenta regresiva y registro local de
resultados. Los umbrales son valores iniciales no validados; no deben
presentarse como detección certificada de sismos ni reemplazan un SOS manual.

## Parámetros iniciales

| Parámetro | Valor |
|---|---:|
| Sensor | `TYPE_ACCELEROMETER`, `SENSOR_DELAY_GAME` (~50 Hz) |
| Filtro paso-alto | alfa 0,8 |
| STA / LTA | 0,5 s / 10 s |
| Umbral STA/LTA | > 3,0 |
| Media de aceleración filtrada | > 0,8 m/s² durante ≥ 3 s |
| Gravedad orientativa | 3: 0,8-<2; 4: 2-4; 5: >4 m/s² |
| Cuenta regresiva | 10 s para nivel 3; 7 s para nivel 4 o 5 |

La gravedad es solo una pista del dispositivo; el servidor sigue siendo la
fuente de autoridad. Sin respuesta, el módulo registra `AUTO_ALERT_TRIGGERED`
y emite una señal local con tipo `A`. El envío de red/SMS no está conectado por
este módulo.

## Filtros y limitaciones conocidas

- Una caída libre seguida de un impacto fuerte queda suprimida temporalmente.
- El movimiento periódico regular de 1-3 Hz se descarta como posible caminata
  o carrera. Este heurístico necesita validación con acelerómetros de distintos
  fabricantes; podría descartar movimiento sísmico periódico.
- No se usa GPS mientras la vigilancia está inactiva, por privacidad. Por ello,
  este módulo tampoco aplica todavía el filtro de vehículo basado en velocidad
  GPS. Solo podría evaluarse después de una detección candidata y con permiso
  de ubicación.
- El movimiento voluntario del teléfono no se puede identificar de manera
  fiable solo con el acelerómetro; se registra como limitación, no se afirma
  que esté resuelto.
- La cuenta regresiva usa notificación de pantalla completa. Android puede
  requerir autorización de pantalla completa/notificaciones y los fabricantes
  pueden suspender servicios. El usuario debe verificar permisos y restricciones
  de batería; un servicio visible no garantiza funcionamiento ante apagado,
  cierre forzado o limitaciones del fabricante.
- Los eventos locales guardan hora, media, pico, razón STA/LTA, gravedad
  estimada y resultado (`DISCARDED`, `USER_OK`, `AUTO_ALERT_TRIGGERED`).
  No se guarda ubicación en esta base.

## Configuración y piloto

Los valores se encapsulan en `DetectionConfig` para que una futura fuente de
configuración remota pueda reemplazarlos sin alterar el algoritmo. El endpoint
de configuración remota no existe todavía en el backend y no se inventa en
este cambio. El piloto debe registrar falsos positivos/negativos, probar
reproducciones de acelerómetro, sacudidas reales controladas y teléfonos de
varias marcas antes de habilitar alertas automáticas.

Para compilar, instalar Android Studio con Android SDK (API 35) y Gradle 8.7 o
superior. Este directorio aún no incluye Gradle Wrapper. Ejecutar desde
`android/`:

```text
gradle testDebugUnitTest
gradle assembleDebug
```
