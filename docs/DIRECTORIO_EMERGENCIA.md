# Directorio de emergencia («Cerca de ti»)

Debajo de los números nacionales (105, 116 y 106) la app puede mostrar la
comisaría, la compañía de bomberos y el centro de salud más cercanos al
usuario. Los números locales complementan a los nacionales; nunca los
reemplazan ni los ocultan.

## Cómo funciona

1. El propietario carga el directorio desde *Administración de propietarios →
   Directorio de emergencia* (archivo CSV) y puede corregir u ocultar entradas.
2. La app descarga el directorio completo con `GET /api/v1/directorio/emergencia`
   y lo guarda en el dispositivo. Ese endpoint es público y no recibe
   coordenadas.
3. El punto más cercano se calcula **en el dispositivo**. La ubicación del
   usuario no se envía al servidor para esto, y el bloque sigue funcionando sin
   conexión con la última copia descargada.
4. La ubicación solo se lee cuando el usuario pulsa «Buscar con mi ubicación»
   o cuando ya se obtuvo para enviar una alerta. No se consulta en reposo.

Por cada tipo se muestra el punto más cercano. Si ese punto no tiene teléfono,
la misma tarjeta agrega el más cercano que sí lo tenga, con su botón de
llamada. No se muestra nada a más de 50 km. La distancia es en línea recta, no
por carretera, y cuando la ubicación es aproximada la app lo dice.

## Formato del archivo CSV

Plantilla: `database/plantillas/directorio_emergencia_plantilla.csv`.

| Columna | Obligatoria | Contenido |
|---|---|---|
| `nombre` | Sí | Nombre del punto (mínimo 3 caracteres). |
| `latitud`, `longitud` | Sí | Grados decimales WGS84, por ejemplo `-7.1575` y `-78.5176`. |
| `tipo` | Sí, salvo que se elija un tipo para todo el archivo | `COMISARIA`, `BOMBEROS`, `SALUD`, `SERENAZGO` u `OTRO`. |
| `telefono` | No | Dígitos, espacios, guiones, paréntesis y `+` inicial. |
| `direccion`, `distrito` | No | Texto libre. |
| `ubicacion_aproximada` | No | `si` cuando las coordenadas son las del poblado y no las del local exacto. La app lo indica junto a la distancia. Vacío o `no` significa ubicación exacta. |

- Se aceptan los CSV de Excel en español: separador `;`, coma decimal y
  codificación Windows-1252.
- También se reconocen nombres de columna habituales (`lat`, `lon`,
  `nombre_comisaria`, `telefono_fijo`…). La respuesta de la carga indica qué
  columna del archivo se usó para cada dato.
- Una entrada se identifica por tipo + nombre + distrito (sin distinguir tildes
  ni mayúsculas). Si ya existe, la carga la actualiza en lugar de duplicarla.
- Las filas inválidas no se guardan y se listan con su número de fila y motivo.
- Cada carga exige la **fuente** de los datos y la **fecha en que se revisó**.
  La app muestra esa fecha junto a cada número y avisa cuando tiene más de 180
  días.

## Reglas para quien administra el directorio

- Cargar solo datos de una fuente oficial o comprobados por llamada. No cargar
  datos de ejemplo: el repositorio no incluye ninguno.
- «Más cercana» no significa «la que tiene jurisdicción»; por eso la app dice
  «más cercana» y mantiene los números nacionales arriba.
- Los teléfonos fijos de dependencias locales pueden no contestar o cambiar.
  Cambiar un teléfono exige anotar de nuevo la fuente y la fecha.

## Datos cargables: departamento de Cajamarca

En `database/directorio/cajamarca/` hay dos archivos listos para cargar,
generados con `scripts/armar_directorio_cajamarca.py` a partir de fuentes
oficiales. Cada uno se carga por separado, con su propia fuente y fecha.

| Archivo | Entradas | Fuente | Fecha a declarar |
|---|---|---|---|
| `directorio_cajamarca_comisarias.csv` | 114 comisarías (66 con teléfono propio) | Prontuario telefónico de las comisarías del Frente Policial Cajamarca, PNP | 17/03/2025 (fecha del documento) |
| `directorio_cajamarca_salud.csv` | 135 centros de salud y hospitales públicos (90 con teléfono) | RENIPRESS – SUSALUD, `IPRESS.csv` de Datos Abiertos | 10/10/2026 (fecha de descarga) |

Lo que hay que saber antes de usarlos:

- **Las coordenadas de las comisarías son aproximadas.** Ninguna fuente
  policial publicada trae coordenadas (ni el prontuario ni la relación nacional
  de comisarías básicas). Cada comisaría se ubicó con las coordenadas del
  establecimiento de salud público del mismo poblado y distrito, tomadas de
  RENIPRESS. Por eso todas llevan `ubicacion_aproximada = si`. El detalle de
  qué establecimiento se usó para cada una está en `INFORME.txt`.
- **En la ciudad de Cajamarca solo se cargó la Comisaría Central**, ubicada con
  la referencia del Centro de Salud Simón Bolívar, a unas cuadras. Dentro de
  la ciudad la distancia mostrada puede fallar por varias cuadras.
- **Cuatro comisarías quedaron fuera** y están en
  `comisarias_pendientes_de_coordenadas.csv`: Familia y San José (ciudad de
  Cajamarca), porque sin la coordenada exacta no se distinguirían de la
  Central, y La Portada y El Salitre, cuyo poblado no tiene un establecimiento
  con ese nombre. Para agregarlas basta completar `latitud` y `longitud` en ese
  archivo y cargarlo. Lo mismo sirve para reemplazar la ubicación aproximada de
  la Central por la exacta.
- **Los teléfonos son los del prontuario oficial.** Otras fuentes (buscadores,
  resúmenes generados por IA, redes sociales) muestran números distintos para
  las mismas comisarías; no se usaron.
- **48 comisarías no tienen teléfono propio**: el prontuario las remite al
  CEOPOL del Frente Policial (980-122-992). Se cargan sin teléfono, así que la
  app prefiere la comisaría cercana que sí tenga uno.
- **El prontuario repite dos números** en comisarías distintas (957-686-547 en
  Baños del Inca y Asunción; 957-804-309 en San Ignacio y Chirinos). Se
  cargaron tal como están en el documento; conviene confirmarlos.
- **El prontuario es de marzo de 2025**: la app mostrará esos números con el
  aviso «puede estar desactualizado» hasta que alguien los vuelva a verificar.
- **Salud**: solo establecimientos públicos (Gobierno Regional, MINSA y
  EsSalud) de categoría I-3 o superior, en funcionamiento. No se incluyeron los
  puestos de salud I-1 e I-2. Los teléfonos fijos de 6 dígitos se completaron
  con el código de área 076. Las coordenadas son las del registro y pueden
  tener errores propios de la fuente.
- **Bomberos**: no se cargó ninguno. El único directorio oficial encontrado
  lista celulares personales de jefes de compañía, sin fecha.

## Pendientes

- Elegir y validar las fuentes oficiales (comisarías, bomberos, salud) y
  definir cada cuánto se vuelve a revisar el directorio.
- Obtener revisión legal de la publicación de estos números.
- La app Android aún no consume este directorio.
- La copia local usa `localStorage`; un directorio de varias decenas de miles
  de entradas no cabría y solo quedaría disponible durante la sesión.
