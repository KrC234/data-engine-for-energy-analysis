# data-engine-for-energy-analysis

Módulo de generación de datos sintéticos del proyecto HyperDataSynthetic (HSD): un sistema de monitoreo de consumo energético para el municipio real de Toluca de Lerdo, Estado de México. El módulo produce los registros del escenario simulado mediante reglas de comportamiento y semillas, de forma que cada corrida sea reproducible y los datos resultantes se inserten en una base PostgreSQL.

## Objetivo

Llevar a cabo la generación de datos sintéticos y la inserción de registros en la base de datos, mediante reglas de comportamiento y el uso de semillas para generar datos lo más cercanos a la realidad.

## Escenario

El escenario es el municipio real de **Toluca** (cabecera: Toluca de Lerdo), capital del Estado de México, con **910.608 habitantes según el Censo de Población y Vivienda 2020 del INEGI** (~24,6% de ellos concentrados en la cabecera municipal). El municipio, en conjunto con la empresa suministradora de electricidad, puso en marcha un programa piloto de medición inteligente: **5.000 puntos de consumo sintéticos** con medidores capaces de transmitir sus lecturas automáticamente, hora tras hora, hacia un centro de monitoreo.

El sistema no monitorea toda la ciudad: monitorea una muestra representativa. De los 5.000 puntos, cerca de cuatro de cada cinco son viviendas particulares. El resto se reparte entre comercios pequeños, edificios públicos como escuelas y clínicas, infraestructura de servicios y elementos de vía pública.

El territorio se organiza en **24 zonas de modelado**, ancladas a localidades y sectores reales de Toluca extraídos del **Catálogo de Localidades y del Índice de Rezago Social por AGEB urbana de CONEVAL (2020)**. El detalle del pipeline de calibración territorial se describe más abajo.

### Naturaleza sintética de los datos

Todos los datos generados por este módulo son **sintéticos**. No corresponden a personas, contratos, medidores ni consumos reales: los puntos de consumo, sus direcciones, números de servicio, series de medidor y lecturas son producidos por reglas y semillas. Lo único que proviene de fuentes oficiales son los **nombres de localidades y sectores** y sus **factores socioeconómicos de referencia**, usados únicamente para que la distribución de los datos sintéticos sea plausible.

### Requisito RD-06 (reescrito conforme a la investigación)

> Los nombres de zona y localidad **pueden** provenir de fuentes oficiales (CONEVAL, INEGI, IMPLAN Toluca) y se emplean tal cual. Lo que **debe** ser sintético y no debe replicar información de personas o contratos reales son: direcciones exactas, números de servicio, series de medidor e identificadores individuales. La regla RD-06 original (prohibición total de fuentes reales) quedó superada por esta reinterpretación validada en `Investigacion_Toluca_Final.docx`.

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

## Calibración territorial

La territorialización sigue un pipeline reproducible construido sobre datos oficiales:

```
CONEVAL: Índice de Rezago Social por AGEB urbana 2020
        (GRS_AGEB_urbana_2020.xlsx)
                │
                ▼
calcular_factores_toluca.py       → factores socioeconómicos por grado de rezago
                │                    Muy bajo = 2.000 · Bajo = 1.625 · Medio = 1.250
                ▼                    Alto = 0.875 · Muy alto = 0.500
GRS_AGEB_Toluca_calibrado.csv     → 264 AGEB de Toluca con factor asignado
                │
                ▼
agrupar_zonas_toluca.py           → agrupa AGEB por localidad y calcula el factor
                │                    representativo ponderado por vivienda
                ▼
Zonas_Toluca_agrupadas.csv        → 46 localidades reales: población, viviendas,
                                     grado de rezago representativo y factor
                │
                ▼
reglas_Pn.json                     → cada integrante ancla sus 4 zonas a localidades
                                     reales y escribe el factor en sus reglas
```

Resultado de la calibración: **46 localidades urbanas de Toluca**, que suman **847.663 habitantes** y **224.104 viviendas habitadas**. Las 24 zonas de modelado se distribuyen entre estas localidades, sin solapamiento entre integrantes.

## Modelo de datos

La base propone 13 tablas clasificadas por el uso de los datos en el sistema:

| Familia | Qué representa | Tablas | Filas esperadas |
|---|---|---|---|
| Catálogos | Conjuntos cerrados de categorías que el sistema reconoce | zona, tarifa, tipo_servicio, tipo_evento | 56 |
| Parámetros | Reglas con las que se generó e interpreta el resto de la información | perfil_carga_horaria, calendario, corrida_generacion | 1.388 |
| Maestras | Inventario de lo que existe físicamente en la ciudad | servicio, medidor | 10.260 |
| Hechos | Lo que ocurre en el tiempo: mediciones, anomalías, alertas, recibos | lectura, evento, alerta, periodo_facturacion | ≈10.844.700 |

Total: ≈10.856.404 filas. Las lecturas concentran más del 99% del volumen.

### Almacenamiento (Decisión E1)

- **Base**: PostgreSQL 15 o superior, con **particionamiento declarativo nativo** por rango mensual sobre la tabla de lecturas. El particionamiento se declara en el esquema y el planificador de PostgreSQL lo gestiona sin lógica de aplicación.
- **Extensión opcional**: TimescaleDB puede instalarse como extensión si el rendimiento agregado lo exige, pero **no es un requisito**: la solución funciona sobre PostgreSQL estándar (decisión E1 del Repositorio de Decisiones).

### Parámetros del escenario

- Puntos de consumo: 5.000.
- Zonas de la ciudad: 24.
- Tipos de punto de consumo: 18.
- Clasificaciones tarifarias: 7.
- Mezcla de servicios por zona: residencial 0.80, comercio 0.10, público 0.06, vía pública 0.04.
- Frecuencia de lectura: una por hora, 24 al día.
- Periodo de observación: 90 días.
- Ciclo de facturación: mensual para todos los servicios.
- Tipos de anomalía: 7.

### Configuración de la corrida maestra

| Parámetro | Valor |
|---|---|
| Semilla raíz | `20260101` |
| Versión de reglas | `1.0.0` |
| Periodo simulado | 1 de enero a 31 de marzo de 2026 |
| Puntos de consumo | 5.000 |
| Retraso de alerta | 1 a 12 horas |
| Probabilidad de falsa alarma | 0.004 |

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

## Metodología

- **Marco rector**: Design Science Research Methodology (DSRM), con generación paramétrica G1 (reglas + semilla).
- **Organización del trabajo**: desarrollo incremental por familias de tablas (catálogos → parámetros → maestras → hechos), con nomenclatura de etapas alineada a CRISP-DM.
- **Reproducibilidad**: dos corridas con la misma semilla y versión de reglas producen resultados idénticos (validado por diff).

## Criterios de aceptación

Conforme a los criterios VA-01…VA-10 del Entregable 1 (v2.1):

| Criterio | Meta |
|---|---|
| Volumen mínimo | ≥ 10 millones de filas insertadas |
| Integridad | 0 violaciones de claves primarias/foráneas, sin nulos en claves, energías no negativas |
| Curva de carga | Desviación ≤ ±15% contra los perfiles declarados |
| Tasas de anomalía | Desviación ≤ ±10% contra las tasas declaradas por tipo |
| Reproducibilidad | Diff vacío entre corridas con la misma semilla y versión |
| Rendimiento | Escritura por lotes, memoria acotada, reanudación sin pérdida ni duplicados |

## Estructura del repositorio

```
data-engine-for-energy-analysis/
├── README.md
├── .gitignore
├── Assignment/
│   └── ASIGNACION_24_ZONAS.md      # reparto de zonas y RD-06
├── Generation/
│   ├── Perfil_de_carga/
│   │   └── Profile_Gen.py          # etapa 3: perfiles de carga horaria
│   └── Zonas/
│       ├── calcular_factores_toluca.py   # calibración CONEVAL → factores
│       ├── agrupar_zonas_toluca.py      # AGEB → 46 localidades reales
│       └── reglas_P1.json               # reglas de P1: zonas 1, 7, 13, 19
└── Rules/
    └── Rules.json                  # reglas versionadas de generación
```

El .gitignore mantiene fuera del repositorio lo que no debe versionarse: entornos virtuales, scripts de inserción con credenciales, catálogos de prueba, resultados de corridas y el punto de entrada principal. Las credenciales de conexión a la base no se suben jamás.

## Cómo usar

### Requisitos

- Python 3.10 o superior, con numpy; pandas se incorpora en las etapas de lecturas.
- PostgreSQL 15 o superior para la base de destino; TimescaleDB opcional (decisión E1).
- Git para el control de versiones.

### Pasos

1. Clonar el repositorio y crear el entorno virtual.
2. Instalar las dependencias del generador: numpy, pandas y el driver de PostgreSQL.
3. Preparar las entradas: `Rules/Rules.json` con las reglas de la corrida y el catálogo de tipos de servicio del escenario.
4. (Territorialización) Ejecutar `Generation/Zonas/calcular_factores_toluca.py` y `agrupar_zonas_toluca.py` con la fuente CONEVAL; las 46 localidades resultantes anclan las 24 zonas.
5. Generar los perfiles de carga horaria ejecutando `Generation/Perfil_de_carga/Profile_Gen.py`; la salida alimenta la tabla perfil_carga_horaria (18 tipos de servicio, 3 tipos de día y 24 horas, 1.296 registros).
6. Correr las etapas en orden: catálogos, parámetros temporales, padrón, anomalías, lecturas, vigilancia y facturación.
7. Insertar en la base por lotes, con commits por bloque y puntos de reanudación.
8. Validar la corrida: conteos por tabla, integridad de claves y reproducibilidad.
9. Construir el datamart y los dashboards sobre los datos validados.

Nota sobre la etapa 3: el catálogo de tipos de servicio vive fuera del repositorio (Test/Testing_data/Tipo_servicio.json), porque la carpeta Test no se versiona. Cada integrante debe contar con ese archivo en la ruta esperada antes de ejecutar el generador de perfiles.

## Reproducibilidad y validación

Dos corridas con la misma semilla y la misma versión de reglas producen resultados idénticos. Para garantizarlo:

- Rules.json se versiona con semver; cada corrida registra la versión usada y la huella de configuración en corrida_generacion.
- Los catálogos son estáticos: el escenario geográfico (24 zonas ancladas a localidades reales) no cambia entre corridas.
- La validación de control compara una corrida de referencia contra la oficial y exige diff vacío.

## Próximos pasos

La etapa de perfiles está implementada y en fase de pruebas. Siguen, en orden: catálogos y parámetros temporales, padrón, sorteo de anomalías, lecturas por lotes con reanudación, vigilancia, facturación, validación integral y el BI sobre el datamart.

## Asignación de tareas y estado del equipo

División de la generación entre 6 personas, 4 zonas por persona (24 zonas de Toluca).
La matriz completa con cuotas, semillas y cronograma vive en `Assignment/ASIGNACION_24_ZONAS.md`;
las plantillas de reglas, en `Generation/Zonas/reglas_Pn.json`. Cada integrante ancla sus
4 zonas a localidades reales del pipeline CONEVAL sin solaparse con los demás (RD-06 reescrita).

| Integrante | Rol | Tareas asignadas | Estado | Rama de trabajo |
|---|---|---|---|---|
| Mateo Jiménez Pérez | Lead base de datos, líder de integración | Corrida maestra, unión de los 6 bloques, semilla raíz, versionado. Zonas 1, 7, 13, 19 | En progreso | dev-mateo |
| David Nieto Ayala | Performance y perfiles | Perfiles de carga (1.296), calendario de 90 días. Zonas 2, 8, 14, 20 | En revisión | dev-david |
| Isabela Mosquera Fernández | Reglas y anomalías | Maestro de Rules.json, sorteo de eventos, tasas. Zonas 3, 9, 15, 21 | En progreso | dev-isabela |
| Aalan Kalid Ruiz Colin | Persistencia | Esquema de 13 tablas, inserción por lotes, checkpoints. Zonas 4, 10, 16, 22 | Pendiente | kalid-dev |
| Sergio Martínez Blas | Validación de integridad | Conteos por tabla, claves, energías no negativas. Zonas 5, 11, 17, 23 | Pendiente | feat/division-zonas-6-personas |
| Ramiro Vega Meza | Reproducibilidad y documentación | Diff entre corridas, guía de reproducción. Zonas 6, 12, 18, 24 | Pendiente | dev |

Estados: Pendiente, En progreso, En revisión, Completado. Los estados reflejan el avance real
del repositorio: la etapa de perfiles (David) está implementada y en pruebas; Rules.json tiene
la versión base 1.0.0 (Isabela la amplía); P1 (Mateo) ya ancló sus 4 zonas a localidades reales.
La generación se trabaja en ramas por tarea y se integra a main por Pull Request, como manda la
política del equipo.

## Reglas de trabajo

- Commits pequeños y descriptivos.
- Integración en una rama de desarrollo; main se mantiene estable.
- Nunca subir credenciales, resultados de corridas ni archivos de prueba al repositorio.
- Cualquier cambio en las reglas de generación sube la versión semver de Rules.json.

El repositorio vive de la disciplina de sus reglas: si las reglas cambian y no sube la versión, las corridas dejan de ser comparables. Ese es el único punto que no admite relajación.