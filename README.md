# data-engine-for-energy-analysis

Módulo de generación de datos sintéticos del proyecto HyperDataSynthetic (HSD): un sistema de monitoreo de consumo energético en una ciudad inteligente. El módulo produce los registros del escenario simulado mediante reglas de comportamiento y semillas, de forma que cada corrida sea reproducible y los datos resultantes se inserten en una base PostgreSQL con TimescaleDB.

## Objetivo

Llevar a cabo la generación de datos sintéticos y la inserción de registros en la base de datos, mediante reglas de comportamiento y el uso de semillas para generar datos lo más cercanos a la realidad.

## Escenario

El Valle de Nexpahuacán es una ciudad ficticia de alrededor de 400.000 habitantes. El municipio, en conjunto con la empresa suministradora de electricidad, puso en marcha un programa piloto de medición inteligente: 5.000 puntos de consumo con medidores capaces de transmitir sus lecturas automáticamente, hora tras hora, hacia un centro de monitoreo.

El sistema no monitorea toda la ciudad: monitorea una muestra representativa. De los 5.000 puntos, cerca de cuatro de cada cinco son viviendas particulares. El resto se reparte entre comercios pequeños, edificios públicos como escuelas y clínicas, infraestructura de servicios y elementos de vía pública.

## Concepto central: dos energías por lectura

Cada lectura horaria almacena dos cantidades de energía, no una:

- **Energía reportada:** el número que salió del aparato y llegó al centro de monitoreo, tal cual, sin corrección alguna. Es lo único que un sistema real conocería.
- **Energía real:** la energía que efectivamente circuló durante esa hora, con independencia de si el medidor la reportó bien, la reportó mal o no la reportó en absoluto. Es la verdad del mundo simulado.

En condiciones normales ambas cantidades coinciden. Cuando ocurre una anomalía se separan, y la forma en que se separan identifica el tipo de anomalía sin ambigüedad.

Casos que el modelo distingue:

- Operación normal: la curva de carga se comporta como se espera y ambos registros coinciden.
- Pérdida de comunicación: la energía real se consumió, mientras que la reportada mantiene valores nulos.
- Medidor congelado o averiado: se consume la energía normal, mientras el medidor reporta un cero constante, hora tras hora.
- Manipulación (fraude): se consume una gran cantidad de energía mientras se reporta una fracción del valor real.
- Pico de demanda: valor por arriba de lo habitual, con ambos registros iguales.
- Consumo legítimamente bajo: valor bajo en periodos esperados.

## Curva de carga y modificadores

El concepto físico que sostiene toda la generación es la curva de carga: la forma en que el consumo de un punto varía a lo largo del día.

Una vivienda consume poco durante la madrugada, algo más por la mañana y alcanza su máximo por la noche. Un mercado municipal presenta la forma opuesta: arranca temprano, culmina a media mañana y prácticamente se apaga de noche. Un circuito de alumbrado público invierte por completo el patrón: consume solo cuando no hay luz solar.

Ese comportamiento obliga a monitorear por hora y a tratar la curva característica como un parámetro almacenado del sistema. Tres modificadores adicionales se aplican de manera multiplicativa sobre la curva: el tipo de día, el carácter socioeconómico de la zona y la estacionalidad.

Las reglas viven en `Rules/Rules.json`, parametrizadas y versionadas. Cada categoría de consumo declara una curva base, una o más gaussianas definidas por centro, ancho, base y amplitud, y modificadores por tipo de día (Hábil, Inhábil, Festivo) que desplazan el pico y escalan la amplitud.

## Modelo de datos

La base propone 13 tablas clasificadas por el uso de los datos en el sistema:

| Familia | Qué representa | Tablas | Filas esperadas |
|---|---|---|---|
| Catálogos | Conjuntos cerrados de categorías que el sistema reconoce | zona, tarifa, tipo_servicio, tipo_evento | 56 |
| Parámetros | Reglas con las que se generó e interpreta el resto de la información | perfil_carga_horaria, calendario, corrida_generacion | 1.388 |
| Maestras | Inventario de lo que existe físicamente en la ciudad | servicio, medidor | 10.260 |
| Hechos | Lo que ocurre en el tiempo: mediciones, anomalías, alertas, recibos | lectura, evento, alerta, periodo_facturacion | ≈10.844.700 |

Total: ≈10.856.404 filas. Las lecturas concentran más del 99% del volumen.

### Parámetros del escenario

- Puntos de consumo: 5.000.
- Zonas de la ciudad: 24.
- Tipos de punto de consumo: 18.
- Clasificaciones tarifarias: 7.
- Frecuencia de lectura: una por hora, 24 al día.
- Periodo de observación: 90 días.
- Ciclo de facturación: mensual para todos los servicios.
- Tipos de anomalía: 7.

### Tipos de evento

Pico de demanda, consumo anómalo sostenido, manipulación del medidor (fraude), falla del medidor, pérdida de comunicación, sobrecarga y mantenimiento programado. Los eventos se sortean antes de generar las lecturas, según las tasas declaradas en las reglas. Las alertas incluyen omisiones y falsas alarmas.

### Encadenamiento de claves

zona 1:N servicio 1:N medidor 1:N lectura, con clave natural de lectura (id_medidor, timestamp) y particionado mensual. Las tarifas solo clasifican, no se modelan como dinero.

## Canalización de ocho etapas

La generación se ejecuta como una canalización de ocho etapas; cada una consume lo producido por las anteriores:

1. Registro de la corrida: semilla, versión de reglas, huella de configuración y alcance temporal.
2. Catálogos: zonas, tarifas, tipos de servicio y tipos de evento.
3. Parámetros temporales: calendario de 90 días con tipo de día y temperatura; perfiles de carga horaria.
4. Padrón: puntos de consumo con zona, tipo y tarifa; medidores con marca, instalación y calidad de comunicación.
5. Anomalías: sucesos con tipo, medidor, inicio, fin e intensidad, sorteados según las tasas declaradas.
6. Lecturas: una fila por medidor y hora, con energía real y energía reportada. Se escribe por lotes para reanudar la carga si algo se interrumpe y para no sostener diez millones de filas en memoria.
7. Vigilancia: alertas emitidas, incluidas omisiones y falsas alarmas.
8. Facturación: un recibo mensual por punto de consumo, con contador inicial y final.

## Estructura del repositorio

```
data-engine-for-energy-analysis/
├── README.md
├── .gitignore
├── Generation/
│   └── Perfil_de_carga/
│       └── Profile_Gen.py      # etapa 3: perfiles de carga horaria
└── Rules/
    └── Rules.json              # reglas versionadas de generación
```

El .gitignore mantiene fuera del repositorio lo que no debe versionarse: entornos virtuales, scripts de inserción con credenciales, catálogos de prueba, resultados de corridas y el punto de entrada principal. Las credenciales de conexión a la base no se suben jamás.

## Cómo usar

### Requisitos

- Python 3.10 o superior, con numpy; pandas se incorpora en las etapas de lecturas.
- PostgreSQL 16 con la extensión TimescaleDB para la base de destino.
- Git para el control de versiones.

### Pasos

1. Clonar el repositorio y crear el entorno virtual.
2. Instalar las dependencias del generador: numpy, pandas y el driver de PostgreSQL.
3. Preparar las entradas: `Rules/Rules.json` con las reglas de la corrida y el catálogo de tipos de servicio del escenario.
4. Generar los perfiles de carga horaria ejecutando `Generation/Perfil_de_carga/Profile_Gen.py`; la salida alimenta la tabla perfil_carga_horaria (18 tipos de servicio, 3 tipos de día y 24 horas, 1.296 registros).
5. Correr las etapas en orden: catálogos, parámetros temporales, padrón, anomalías, lecturas, vigilancia y facturación.
6. Insertar en la base por lotes, con commits por bloque y puntos de reanudación.
7. Validar la corrida: conteos por tabla, integridad de claves y reproducibilidad.
8. Construir el datamart y los dashboards sobre los datos validados.

Nota sobre la etapa 3: el catálogo de tipos de servicio vive fuera del repositorio (Test/Testing_data/Tipo_servicio.json), porque la carpeta Test no se versiona. Cada integrante debe contar con ese archivo en la ruta esperada antes de ejecutar el generador de perfiles.

## Reproducibilidad y validación

Dos corridas con la misma semilla y la misma versión de reglas producen resultados idénticos. Para garantizarlo:

- Rules.json se versiona con semver; cada corrida registra la versión usada y la huella de configuración en corrida_generacion.
- Los catálogos son estáticos: el escenario geográfico no cambia entre corridas.
- La validación de control compara una corrida de referencia contra la oficial y exige diff vacío.

Criterios de aceptación medibles:

- Volumen: al menos 10 millones de filas insertadas.
- Reproducibilidad: dos corridas con la misma semilla y versión de reglas, idénticas.
- Integridad: claves primarias y foráneas válidas, sin nulos en las claves y energías no negativas.
- Tasas: eventos y alertas coherentes con las reglas declaradas.
- Rendimiento: escritura por lotes, memoria acotada y reanudación sin duplicar ni perder lecturas.

## Próximos pasos

La etapa de perfiles está implementada y en fase de pruebas. Siguen, en orden: catálogos y parámetros temporales, padrón, sorteo de anomalías, lecturas por lotes con reanudación, vigilancia, facturación, validación integral y el BI sobre el datamart.

## Reglas de trabajo

- Commits pequeños y descriptivos.
- Integración en una rama de desarrollo; main se mantiene estable.
- Nunca subir credenciales, resultados de corridas ni archivos de prueba al repositorio.
- Cualquier cambio en las reglas de generación sube la versión semver de Rules.json.

El repositorio vive de la disciplina de sus reglas: si las reglas cambian y no sube la versión, las corridas dejan de ser comparables. Ese es el único punto que no admite relajación.