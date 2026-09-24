======================================================================
⚡ HYPERDATASYNTHETIC
======================================================================

Motor de generación de datos hiper-sintéticos para simular el consumo
energético de un programa de medición inteligente en el municipio de
Toluca, Estado de México.

El proyecto genera información mediante reglas explícitas y
reproducibles, sin utilizar lecturas eléctricas individuales reales.


📌 CONTENIDO
======================================================================

  01. Objetivo
  02. Principio de Hyper-Synthetic Data
  03. Arquitectura actual
  04. Configuración
  05. Base de datos
  06. Generadores
  07. Modelo de datos
  08. Flujo de generación
  09. Generación del consumo
  10. Consumo real y consumo reportado
  11. Generación por lotes
  12. Configuración de PostgreSQL
  13. Preparación del entorno
  14. Creación inicial de la base
  15. Comprobación desde Python
  16. Validación de catálogos
  17. Estado actual
  18. Próximo paso


======================================================================
🎯 01. OBJETIVO
======================================================================

Construir una base de datos PostgreSQL con información sintética
relacionada con:

  • Zonas de Toluca
  • Servicios eléctricos
  • Medidores inteligentes
  • Calendario y temperatura
  • Perfiles horarios de consumo
  • Eventos y anomalías
  • Lecturas energéticas
  • Alertas
  • Periodos de facturación


📊 Escenario principal

  Servicios sintéticos ............... 5,000
  Medidores activos .................. 5,000
  Periodo ............................ 90 días
  Intervalo de lectura ............... 1 hora
  Lecturas por medidor/día ........... 24


📈 Volumen esperado

  5,000 medidores
     ×
     90 días
     ×
     24 lecturas
     │
     ▼
  10,800,000 lecturas


======================================================================
🧬 02. PRINCIPIO DE HYPER-SYNTHETIC DATA
======================================================================

Los datos NO se copian de medidores eléctricos reales.

Cada registro se construye utilizando reglas conocidas:

  Configuración
       +
  Catálogos
       +
  Perfiles horarios
       +
  Factores territoriales
       +
  Variación pseudoaleatoria controlada
       │
       ▼
  Datos hiper-sintéticos


🔁 REPRODUCIBILIDAD

La misma semilla + las mismas reglas + la misma configuración
deben producir el mismo resultado.


======================================================================
📂 03. ARQUITECTURA ACTUAL
======================================================================

data-engine-for-energy-analysis/
│
├── config/
│   ├── config_loader.py
│   ├── generation.yaml
│   ├── rules.yaml
│   └── settings.py
│
├── database/
│   │
│   ├── sql/
│   │   ├── 01_esquema.sql
│   │   └── 02_catalogos.sql
│   │
│   ├── connection.py
│   ├── database_check.py
│   └── partition_manager.py
│
├── Generation/
│   ├── Dispositivos_Gen.py
│   ├── Profile_Gen.py
│   └── Servicios_Gen.py
│
├── calculos/
│
├── .env
├── .gitignore
├── main.py
├── README.md
└── requirements.txt


======================================================================
⚙️ 04. CONFIGURACIÓN
======================================================================

📁 config/

Contiene la configuración general del proyecto.


📄 generation.yaml
----------------------------------------------------------------------

Define el alcance de una corrida de generación:

  • Nombre
  • Semilla
  • Fecha inicial
  • Fecha final
  • Intervalo de lectura
  • Número de servicios
  • Tamaño de lote
  • Funcionalidades habilitadas

En otras palabras:

  ❓ ¿QUÉ cantidad de datos se va a generar?


📄 rules.yaml
----------------------------------------------------------------------

Contiene las reglas utilizadas por los generadores:

  • Distribución de servicios
  • Probabilidad de generación solar
  • Ocupación residencial
  • Carga contratada
  • Marcas de medidores
  • Calidad de enlace
  • Temperaturas
  • Factores estacionales
  • Variación aleatoria del consumo

En otras palabras:

  ❓ ¿CÓMO deben comportarse los datos generados?


📄 config_loader.py
----------------------------------------------------------------------

Lee:

  • generation.yaml
  • rules.yaml

Evita que cada generador tenga que abrir manualmente los archivos
de configuración.


📄 settings.py
----------------------------------------------------------------------

Lee las variables almacenadas en:

  .env

Contiene la configuración necesaria para establecer la conexión
con PostgreSQL.


======================================================================
🗄️ 05. BASE DE DATOS
======================================================================

📁 database/

Contiene la infraestructura de acceso y despliegue de PostgreSQL.


📄 database/sql/01_esquema.sql
----------------------------------------------------------------------

Crea:

  ✓ Esquema "energia"
  ✓ 13 tablas principales
  ✓ Restricciones
  ✓ Índices
  ✓ Particiones mensuales de "lectura"


📄 database/sql/02_catalogos.sql
----------------------------------------------------------------------

Carga los datos fijos del sistema:

  Zonas o localidades de Toluca ...... 46
  Tarifas ............................. 7
  Tipos de servicio .................. 18
  Tipos de evento .................... 7
  Perfiles horarios .................. 1,296


Los perfiles horarios se calculan como:

  18 tipos de servicio
      ×
   3 tipos de día
      ×
  24 horas
      │
      ▼
  1,296 perfiles


📄 connection.py
----------------------------------------------------------------------

Abre la conexión entre Python y PostgreSQL utilizando las variables
definidas en ".env".


📄 database_check.py
----------------------------------------------------------------------

Comprueba que estén disponibles:

  ✓ Base de datos
  ✓ Esquema
  ✓ Tablas necesarias


📄 partition_manager.py
----------------------------------------------------------------------

Administra las particiones mensuales de:

  energia.lectura


======================================================================
🏭 06. GENERADORES
======================================================================

📁 Generation/

Esta carpeta contendrá los programas responsables de generar los
datos variables.

Arquitectura prevista:

Generation/
│
├── Calendario_Gen.py
├── Servicios_Gen.py
├── Dispositivos_Gen.py
├── Eventos_Gen.py
├── Lecturas_Gen.py
├── Alertas_Gen.py
├── Facturacion_Gen.py
└── Generador.py


Cada archivo tendrá una responsabilidad específica.

⚠️ IMPORTANTE

Esta es la arquitectura prevista.

No significa que todos estos componentes se encuentren actualmente
implementados.


======================================================================
🗃️ 07. MODELO DE DATOS
======================================================================

La base contiene 13 tablas principales.


📚 CATÁLOGOS
----------------------------------------------------------------------

  • zona
  • tarifa
  • tipo_servicio
  • tipo_evento


⚙️ PARÁMETROS
----------------------------------------------------------------------

  • perfil_carga_horaria
  • calendario
  • corrida_generacion


🏠 DATOS MAESTROS
----------------------------------------------------------------------

  • servicio
  • medidor


📊 HECHOS
----------------------------------------------------------------------

  • evento
  • lectura
  • alerta
  • periodo_facturacion


Visualmente:

  ┌──────────────────────────────┐
  │         📚 CATÁLOGOS         │
  │                              │
  │  zona                        │
  │  tarifa                      │
  │  tipo_servicio               │
  │  tipo_evento                 │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │         ⚙️ PARÁMETROS        │
  │                              │
  │  perfil_carga_horaria        │
  │  calendario                  │
  │  corrida_generacion          │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │       🏠 DATOS MAESTROS      │
  │                              │
  │  servicio                    │
  │  medidor                     │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │          📊 HECHOS           │
  │                              │
  │  evento                      │
  │  lectura                     │
  │  alerta                      │
  │  periodo_facturacion         │
  └──────────────────────────────┘


======================================================================
🔄 08. FLUJO DE GENERACIÓN
======================================================================

El flujo general previsto es:


  01_esquema.sql
        │
        ▼
  🗄️ Crear estructura
        │
        ▼
  02_catalogos.sql
        │
        ▼
  📚 Cargar catálogos
        │
        ▼
  Calendario_Gen.py
        │
        ▼
  📅 Generar 90 días
        │
        ▼
  Servicios_Gen.py
        │
        ▼
  🏠 Generar 5,000 servicios
        │
        ▼
  Dispositivos_Gen.py
        │
        ▼
  📟 Generar medidores
        │
        ▼
  Eventos_Gen.py
        │
        ▼
  ⚠️ Generar anomalías
        │
        ▼
  Lecturas_Gen.py
        │
        ▼
  ⚡ Generar 10,800,000 lecturas
        │
        ▼
  Alertas_Gen.py
        │
        ▼
  🚨 Simular detección
        │
        ▼
  Facturacion_Gen.py
        │
        ▼
  🧾 Generar periodos mensuales


======================================================================
⚡ 09. GENERACIÓN DEL CONSUMO
======================================================================

Para cada medidor y cada hora se calculará:


  consumo_real
       =
  consumo_base
       ×
  perfil_horario
       ×
  factor_socioeconomico
       ×
  factor_estacional
       ×
  variacion_aleatoria


📍 ORIGEN DE CADA COMPONENTE
----------------------------------------------------------------------

consumo_base
└── energia.tipo_servicio

perfil_horario
└── energia.perfil_carga_horaria

factor_socioeconomico
└── energia.zona

factor_estacional
└── energia.calendario

variacion_aleatoria
└── config/rules.yaml


🧪 EJEMPLO
----------------------------------------------------------------------

Consumo base ......................... 0.350
Perfil horario ....................... 2.180
Factor socioeconómico ................ 1.250
Factor estacional .................... 1.080
Variación aleatoria .................. 0.970


Operación:

  0.350 × 2.180 × 1.250 × 1.080 × 0.970

Resultado:

  ≈ 0.999 kWh


======================================================================
🔍 10. CONSUMO REAL Y CONSUMO REPORTADO
======================================================================

Cada lectura contiene dos valores:

  consumo_real_kwh
  consumo_kwh


✅ OPERACIÓN NORMAL
----------------------------------------------------------------------

  consumo_kwh = consumo_real_kwh


⚠️ OPERACIÓN CON ANOMALÍA
----------------------------------------------------------------------

El consumo reportado puede ser diferente al consumo real.


📈 