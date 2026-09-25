# ⚡ HyperDataSynthetic

Motor de generación de datos hiper-sintéticos para simular el consumo energético de un programa de medición inteligente en el municipio de Toluca, Estado de México.

El proyecto construye información mediante reglas explícitas, configurables y reproducibles. No utiliza lecturas eléctricas individuales reales.

---

## Contenido

1. [Objetivo](#1-objetivo)
2. [Principio de datos hiper-sintéticos](#2-principio-de-datos-hiper-sintéticos)
3. [Requisitos](#3-requisitos)
4. [Instalación](#4-instalación)
5. [Preparación de PostgreSQL](#5-preparación-de-postgresql)
6. [Configuración](#6-configuración)
7. [Ejecución](#7-ejecución)
8. [Comandos disponibles](#8-comandos-disponibles)
9. [Restablecer los datos generados](#9-restablecer-los-datos-generados)
10. [Comprobar el resultado](#10-comprobar-el-resultado)
11. [Arquitectura](#11-arquitectura)
12. [Generadores](#12-generadores)
13. [Modelo de datos](#13-modelo-de-datos)
14. [Flujo de generación](#14-flujo-de-generación)
15. [Generación del consumo](#15-generación-del-consumo)
16. [Consumo real y consumo reportado](#16-consumo-real-y-consumo-reportado)
17. [Registro de corridas](#17-registro-de-corridas)
18. [Pruebas y diagnóstico](#18-pruebas-y-diagnóstico)
19. [Solución de problemas](#19-solución-de-problemas)

---

## 1. Objetivo

Construir una base de datos PostgreSQL con información sintética relacionada con:

- Zonas de Toluca
- Servicios eléctricos
- Medidores inteligentes
- Calendario y temperatura
- Perfiles horarios de consumo
- Eventos y anomalías
- Lecturas energéticas
- Alertas
- Periodos mensuales de facturación
- Registro y trazabilidad de corridas

### Escenario principal

```text
Servicios sintéticos ............... 5,000
Medidores iniciales ................ 5,000
Medidores de reemplazo ............. 260
Periodo ............................ 90 días
Intervalo de lectura ............... 60 minutos
Lecturas por medidor/día ........... 24
```

### Volumen base esperado

```text
5,000 servicios
    ×
90 días
    ×
24 lecturas diarias
    =
10,800,000 lecturas base
```

Los reemplazos no deben duplicar lecturas. Cada medidor genera lecturas únicamente dentro de su periodo de vigencia, desde `fecha_instalacion` hasta `fecha_retiro`.

---

## 2. Principio de datos hiper-sintéticos

Los datos no se copian de medidores eléctricos reales. Cada registro se construye a partir de:

```text
Configuración
     +
Catálogos PostgreSQL
     +
Perfiles horarios
     +
Factores territoriales
     +
Calendario y temperatura
     +
Variación pseudoaleatoria controlada
     =
Datos hiper-sintéticos reproducibles
```

### Reproducibilidad

La misma semilla, las mismas reglas, los mismos catálogos y la misma configuración deben producir resultados equivalentes.

Cada corrida puede registrar:

- Nombre
- Semilla
- Versión de reglas
- Fechas
- Intervalo
- Hash SHA-256 de configuración y reglas
- Hora de inicio
- Hora de finalización
- Estado
- Total de lecturas
- Mensaje de error, si aplica

---

## 3. Requisitos

### Software

- Python 3.11 o superior
- PostgreSQL
- PowerShell, Terminal o consola equivalente
- Git, opcional

### Dependencias de Python

El archivo `requirements.txt` incluye:

```text
PyYAML==6.0.3
numpy==2.5.3
psycopg[binary]==3.3.6
python-dotenv
pytest
```

---

## 4. Instalación

Todos los comandos deben ejecutarse desde la raíz del proyecto.

### 4.1 Crear el entorno virtual

En PowerShell:

```powershell
py -m venv .venv
```

### 4.2 Activar el entorno virtual

```powershell
.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, ejecuta una vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Después vuelve a activar:

```powershell
.venv\Scripts\Activate.ps1
```

La terminal debe mostrar algo parecido a:

```text
(.venv) PS C:\ruta\data-engine-for-energy-analysis>
```

### 4.3 Actualizar pip

```powershell
python -m pip install --upgrade pip
```

### 4.4 Instalar todas las dependencias

```powershell
python -m pip install -r requirements.txt
```

### 4.5 Verificar las dependencias

```powershell
python -m pip check
```

Resultado esperado:

```text
No broken requirements found.
```

Comprueba las importaciones principales:

```powershell
python -c "import yaml, numpy, psycopg, dotenv, pytest; print('Dependencias OK')"
```

---

## 5. Preparación de PostgreSQL

### 5.1 Configurar `.env`

Crea un archivo `.env` en la raíz del proyecto con los nombres de variables que utiliza `database/connection.py` o `config/settings.py`.

Ejemplo orientativo:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=hyperdatasynthetic
DB_USER=postgres
DB_PASSWORD=CAMBIA_ESTA_CONTRASENA
DB_SCHEMA=energia
```

No subas `.env` al repositorio. Inclúyelo en `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
```

### 5.2 Crear la base de datos

Si la base todavía no existe:

```powershell
createdb -h localhost -p 5432 -U postgres hyperdatasynthetic
```

También puedes crearla desde pgAdmin.

### 5.3 Crear el esquema y las tablas

```powershell
psql -h localhost -p 5432 -U postgres -d hyperdatasynthetic -f database/sql/01_esquema.sql
```

### 5.4 Cargar los catálogos

```powershell
psql -h localhost -p 5432 -U postgres -d hyperdatasynthetic -f database/sql/02_catalogos.sql
```

Los catálogos deben conservarse entre corridas:

- `energia.zona`
- `energia.tarifa`
- `energia.tipo_servicio`
- `energia.tipo_evento`

Según el diseño de la base, `02_catalogos.sql` también puede cargar `energia.perfil_carga_horaria`.

### 5.5 Probar la conexión desde Python

```powershell
python -c "from database.connection import get_connection; c=get_connection(); print('Conexion PostgreSQL OK'); c.close()"
```

### 5.6 Comprobar catálogos

Ejecuta en pgAdmin o `psql`:

```sql
SELECT 'zona' AS tabla, COUNT(*) AS registros
FROM energia.zona
UNION ALL
SELECT 'tarifa', COUNT(*) FROM energia.tarifa
UNION ALL
SELECT 'tipo_servicio', COUNT(*) FROM energia.tipo_servicio
UNION ALL
SELECT 'tipo_evento', COUNT(*) FROM energia.tipo_evento
ORDER BY tabla;
```

Todos los conteos deben ser mayores que cero.

---

## 6. Configuración

### `config/generation.yaml`

Define cuánto se genera y qué funcionalidades se habilitan.

Ejemplo:

```yaml
generation:
  name: "toluca_hsd_90_dias"
  seed: 20260101
  rules_version: "2.0.0"

  start_date: "2026-01-01"
  end_date: "2026-03-31"

  reading_interval_minutes: 60

  services: 5000
  active_meters: 5000
  replacement_meters: 260

  territory: "Toluca, Estado de Mexico"
  batch_size: 100000

  service_generation:
    replace_existing: true

performance:
  batch_size: 100000
  workers: 1
  queue_size: 2

features:
  events: true
  alerts: true
  billing: true
  solar: true
  meter_replacements: true

validation:
  enabled: true
  minimum_total_records: 10000000
  expected_readings: 10800000
  integrity_check: true
  reproducibility_check: true
```

### `config/rules.yaml`

Define cómo deben comportarse los datos:

- Distribución de categorías
- Probabilidad solar
- Ocupación residencial
- Carga contratada
- Coordenadas
- Altitud auxiliar
- Marcas de medidores
- Calidad de enlace
- Multiplicadores
- Temperatura
- Factores estacionales
- Festivos y vacaciones
- Variación del consumo

Ejemplo de marcas:

```yaml
meters:
  brands:
    MEDISUR: 0.35
    KRONOS: 0.35
    NOVAMET: 0.30
```

Los pesos deben sumar `1.0`.

---

## 7. Ejecución

### 7.1 Ver ayuda

Este comando no genera datos:

```powershell
python main.py --help
```

### 7.2 Primera ejecución

Si las tablas de generación están vacías:

```powershell
python main.py
```

### 7.3 Limpiar y volver a generar

Si `--reset` está configurado para limpiar y continuar, ejecuta:

```powershell
python main.py --reset --force
```

El flujo será:

```text
Limpiar los datos generados
        ↓
Conservar los catálogos
        ↓
Registrar una nueva corrida
        ↓
Ejecutar todos los generadores
        ↓
Validar PostgreSQL
        ↓
Mostrar una muestra
```

### 7.4 Prueba pequeña

```powershell
python main.py --reset --force --servicios 10 --dias 2
```

Para 10 servicios, 2 días e intervalo de 60 minutos se esperan aproximadamente 480 lecturas base, sin considerar errores de vigencia o configuración.

### 7.5 Modo demostración

```powershell
python main.py --reset --force --demo
```

### 7.6 Ejecutar sin muestra final

```powershell
python main.py --sin-muestra
```

### 7.7 Ejecutar una sola etapa

```powershell
python main.py --solo Calendario
```

Otros ejemplos:

```powershell
python main.py --solo Perfiles
python main.py --solo Servicios
python main.py --solo Dispositivos
python main.py --solo Eventos
python main.py --solo Lecturas
python main.py --solo Alertas
python main.py --solo Facturacion
```

Una etapa aislada puede requerir que sus tablas dependientes ya contengan datos.

---

## 8. Comandos disponibles

### Ejecución normal

```powershell
python main.py
```

### Cambiar servicios temporalmente

```powershell
python main.py --servicios 200
```

### Cambiar días temporalmente

```powershell
python main.py --dias 7
```

### Cambiar ambos

```powershell
python main.py --servicios 200 --dias 7
```

### Limpiar y generar de nuevo

```powershell
python main.py --reset --force
```

### Limpiar y ejecutar una prueba pequeña

```powershell
python main.py --reset --force --servicios 10 --dias 2
```

### Ejecutar pruebas automatizadas

```powershell
python -m pytest -v
```

### Validar sintaxis de todo el proyecto

```powershell
python -m compileall main.py database Generation
```

### Validar importaciones

```powershell
python -c "import main; print('Importaciones del proyecto OK')"
```

---

## 9. Restablecer los datos generados

El reset debe eliminar los datos variables sin borrar los catálogos.

Tablas que normalmente se limpian:

- `energia.alerta`
- `energia.periodo_facturacion`
- `energia.lectura`
- `energia.evento`
- `energia.medidor`
- `energia.servicio`
- `energia.calendario`
- `energia.corrida_generacion`

El comando recomendado es:

```powershell
python main.py --reset --force
```

La implementación utiliza `CONTINUE IDENTITY` para evitar errores cuando el usuario de la aplicación no es propietario de alguna secuencia:

```sql
TRUNCATE TABLE ... CONTINUE IDENTITY CASCADE;
```

Esto elimina los registros, pero las secuencias pueden continuar desde su último valor.

### Limpieza manual alternativa

```sql
TRUNCATE TABLE
    energia.alerta,
    energia.periodo_facturacion,
    energia.lectura,
    energia.evento,
    energia.medidor,
    energia.servicio,
    energia.calendario,
    energia.corrida_generacion
CONTINUE IDENTITY CASCADE;
```

No incluyas los catálogos en esta limpieza.

---

## 10. Comprobar el resultado

### Comprobar tablas generadas

```sql
SELECT 'alerta' AS tabla, COUNT(*) AS registros FROM energia.alerta
UNION ALL
SELECT 'calendario', COUNT(*) FROM energia.calendario
UNION ALL
SELECT 'corrida_generacion', COUNT(*) FROM energia.corrida_generacion
UNION ALL
SELECT 'evento', COUNT(*) FROM energia.evento
UNION ALL
SELECT 'lectura', COUNT(*) FROM energia.lectura
UNION ALL
SELECT 'medidor', COUNT(*) FROM energia.medidor
UNION ALL
SELECT 'periodo_facturacion', COUNT(*) FROM energia.periodo_facturacion
UNION ALL
SELECT 'servicio', COUNT(*) FROM energia.servicio
ORDER BY tabla;
```

### Resultado esperado después de un reset sin regeneración

```text
alerta                  0
calendario              0
corrida_generacion      0
evento                  0
lectura                 0
medidor                 0
periodo_facturacion     0
servicio                0
```

### Consultar las últimas corridas

```sql
SELECT *
FROM energia.corrida_generacion
ORDER BY id_corrida DESC;
```

Si existen las columnas extendidas:

```sql
SELECT
    id_corrida,
    nombre,
    semilla,
    version_reglas,
    hash_parametros,
    ts_inicio_ejecucion,
    ts_fin_ejecucion,
    fecha_desde,
    fecha_hasta,
    intervalo_min,
    total_lecturas,
    estado,
    mensaje_error
FROM energia.corrida_generacion
ORDER BY id_corrida DESC;
```

### Comprobar una muestra de lecturas

```sql
SELECT
    s.id_servicio,
    s.nombre,
    m.numero_serie,
    l.ts,
    l.consumo_kwh,
    l.consumo_real_kwh,
    l.id_evento
FROM energia.lectura l
JOIN energia.medidor m
  ON m.id_medidor = l.id_medidor
JOIN energia.servicio s
  ON s.id_servicio = m.id_servicio
ORDER BY l.ts, l.id_medidor
LIMIT 20;
```

---

## 11. Arquitectura

```text
data-engine-for-energy-analysis/
│
├── config/
│   ├── config_loader.py
│   ├── generation.yaml
│   ├── rules.yaml
│   └── settings.py
│
├── database/
│   ├── sql/
│   │   ├── 01_esquema.sql
│   │   └── 02_catalogos.sql
│   ├── connection.py
│   ├── database_check.py
│   ├── insertar.py
│   └── partition_manager.py
│
├── Generation/
│   ├── Calendario_Gen.py
│   ├── Profile_Gen.py
│   ├── Servicios_Gen.py
│   ├── Dispositivos_Gen.py
│   ├── Eventos_Gen.py
│   ├── Lecturas_Gen.py
│   ├── Alertas_Gen.py
│   └── Facturacion_Gen.py
│
├── tests/
├── .env
├── .gitignore
├── main.py
├── README.md
└── requirements.txt
```

---

## 12. Generadores

### `Calendario_Gen.py`

Genera fechas, tipos de día, temperatura y factores estacionales.

### `Profile_Gen.py`

Genera perfiles horarios por tipo de servicio y tipo de día, o valida los perfiles cargados en PostgreSQL según la versión del proyecto.

### `Servicios_Gen.py`

Genera servicios y asigna:

- Zona
- Tipo de servicio
- Tarifa
- RPU
- Coordenadas
- Ocupación residencial
- Carga contratada
- Generación solar

### `Dispositivos_Gen.py`

Genera medidores iniciales y reemplazos:

- Número de serie
- Marca ponderada
- Modelo
- Fecha de instalación
- Fecha de retiro
- Estado

Cuando existe un reemplazo, el medidor anterior debe retirarse y el nuevo debe quedar activo.

### `Eventos_Gen.py`

Genera anomalías asociadas a medidores dentro del periodo configurado.

### `Lecturas_Gen.py`

Genera lecturas por intervalo, respeta la vigencia de cada medidor, aplica perfiles, temperatura, ocupación, factor socioeconómico, estacionalidad, variación aleatoria, solar y eventos.

### `Alertas_Gen.py`

Genera alertas a partir de eventos detectados y de las reglas de detección.

### `Facturacion_Gen.py`

Genera periodos mensuales por servicio y conserva:

- Folio
- Fecha inicial y final
- Tarifa aplicada
- Registro inicial
- Registro final
- Consumo real
- Clasificación DAC

---

## 13. Modelo de datos

### Catálogos

- `zona`
- `tarifa`
- `tipo_servicio`
- `tipo_evento`

### Parámetros

- `perfil_carga_horaria`
- `calendario`
- `corrida_generacion`

### Datos maestros

- `servicio`
- `medidor`

### Hechos

- `evento`
- `lectura`
- `alerta`
- `periodo_facturacion`

```text
CATÁLOGOS
    ↓
PARÁMETROS
    ↓
SERVICIOS Y MEDIDORES
    ↓
EVENTOS, LECTURAS Y ALERTAS
    ↓
PERIODOS DE FACTURACIÓN
```

---

## 14. Flujo de generación

```text
01_esquema.sql
      ↓
Crear estructura PostgreSQL
      ↓
02_catalogos.sql
      ↓
Cargar catálogos
      ↓
Calendario_Gen.py
      ↓
Profile_Gen.py
      ↓
Servicios_Gen.py
      ↓
Dispositivos_Gen.py
      ↓
Eventos_Gen.py
      ↓
Lecturas_Gen.py
      ↓
Alertas_Gen.py
      ↓
Facturacion_Gen.py
      ↓
Validación final
      ↓
Cierre de corrida
```

---

## 15. Generación del consumo

Para cada medidor e instante se calcula conceptualmente:

```text
consumo_real
    =
consumo_base
    ×
factor_perfil_horario
    ×
factor_individual
    ×
factor_ocupacion
    ×
factor_socioeconomico
    ×
factor_estacional
    ×
factor_temperatura
    ×
variacion_aleatoria
    ×
factor_solar
    ×
fraccion_del_intervalo
    ×
multiplicador
```

### Origen de los componentes

```text
consumo_base
└── energia.tipo_servicio

factor_perfil_horario
└── energia.perfil_carga_horaria

factor_ocupacion
└── energia.servicio.ocupacion_estimada

factor_socioeconomico
└── energia.zona

factor_estacional y temperatura
└── energia.calendario

variacion_aleatoria y solar
└── config/rules.yaml

multiplicador
└── energia.medidor
```

### Ejemplo simplificado

```text
Consumo base ......................... 0.350
Perfil horario ....................... 2.180
Factor socioeconómico ................ 1.250
Factor estacional .................... 1.080
Variación aleatoria .................. 0.970
```

```text
0.350 × 2.180 × 1.250 × 1.080 × 0.970 ≈ 0.999 kWh
```

---

## 16. Consumo real y consumo reportado

Cada lectura contiene:

```text
consumo_real_kwh
consumo_kwh
```

### Operación normal

```text
consumo_kwh = consumo_real_kwh
```

### Operación con anomalía

El consumo reportado puede diferir del real:

```text
INCREMENTO
consumo_kwh = consumo_real_kwh × intensidad

REDUCCION
consumo_kwh = consumo_real_kwh × intensidad

CONGELAMIENTO
consumo_kwh = ultimo valor reportado

NULIFICACION
consumo_kwh = NULL
```

`Facturacion_Gen.py` puede diferenciar el consumo registrado por el contador del consumo real estimado mediante la propiedad `afecta_acumulado` del tipo de evento.

---

## 17. Registro de corridas

Si existe `energia.corrida_generacion`, `main.py` registra la ejecución.

Estados posibles:

```text
EN_PROCESO
COMPLETADA
ERROR
CANCELADA
```

El hash SHA-256 se obtiene del contenido completo normalizado de:

- `generation.yaml`
- `rules.yaml`

Esto permite identificar cambios en parámetros y reglas.

Una tabla recomendada puede incluir:

```sql
CREATE TABLE IF NOT EXISTS energia.corrida_generacion (
    id_corrida BIGINT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    semilla BIGINT NOT NULL,
    version_reglas VARCHAR(50),
    hash_parametros VARCHAR(64) NOT NULL,
    ts_inicio_ejecucion TIMESTAMP NOT NULL,
    ts_fin_ejecucion TIMESTAMP,
    fecha_desde DATE NOT NULL,
    fecha_hasta DATE NOT NULL,
    intervalo_min INTEGER NOT NULL,
    total_lecturas BIGINT DEFAULT 0,
    estado VARCHAR(20) DEFAULT 'EN_PROCESO',
    mensaje_error TEXT
);
```

Antes de crearla, revisa si `01_esquema.sql` ya incluye una definición de esta tabla.

---

## 18. Pruebas y diagnóstico

### Ejecutar pruebas

```powershell
python -m pytest -v
```

### Comprobar sintaxis

```powershell
python -m compileall main.py database Generation
```

### Comprobar paquetes

```powershell
python -m pip check
```

### Comprobar importación principal

```powershell
python -c "import main; print('Proyecto importado correctamente')"
```

### Comprobar versión de dependencias

```powershell
python -c "import yaml, numpy, psycopg; print('PyYAML', yaml.__version__); print('NumPy', numpy.__version__); print('Psycopg', psycopg.__version__)"
```

### Comprobar estructura PostgreSQL

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'energia'
ORDER BY table_name;
```

---

## 19. Solución de problemas

### Error: `ModuleNotFoundError`

Activa el entorno e instala las dependencias:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Error: conexión PostgreSQL

Revisa:

- PostgreSQL está iniciado
- La base existe
- `.env` contiene credenciales correctas
- `database/connection.py` utiliza los mismos nombres de variables

Prueba:

```powershell
python -c "from database.connection import get_connection; c=get_connection(); print('Conexion OK'); c.close()"
```

### Error: `must be owner of sequence ...`

El reset no debe usar `RESTART IDENTITY` si el usuario no es propietario de las secuencias.

Usa:

```sql
CONTINUE IDENTITY
```

### Error: ya existen servicios o lecturas

Limpia y genera nuevamente:

```powershell
python main.py --reset --force
```

### Error: faltan perfiles horarios

Ejecuta el generador de perfiles o vuelve a cargar los catálogos, según la arquitectura elegida:

```powershell
python main.py --solo Perfiles
```

O:

```powershell
psql -h localhost -p 5432 -U postgres -d hyperdatasynthetic -f database/sql/02_catalogos.sql
```

### Error: faltan tablas

Ejecuta nuevamente el esquema:

```powershell
psql -h localhost -p 5432 -U postgres -d hyperdatasynthetic -f database/sql/01_esquema.sql
```

### Error de validación en las lecturas

Comprueba:

- Intervalo configurado
- Fechas de instalación y retiro
- Medidores de reemplazo
- Rango del calendario
- Existencia de perfiles
- Lecturas duplicadas

---

## Secuencia rápida de instalación y ejecución

Para un proyecto recién descargado:

```powershell
# 1. Crear entorno
py -m venv .venv

# 2. Activar entorno
.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4. Comprobar dependencias
python -m pip check

# 5. Crear estructura PostgreSQL
psql -h localhost -p 5432 -U postgres -d hyperdatasynthetic -f database/sql/01_esquema.sql

# 6. Cargar catálogos
psql -h localhost -p 5432 -U postgres -d hyperdatasynthetic -f database/sql/02_catalogos.sql

# 7. Validar sintaxis
python -m compileall main.py database Generation

# 8. Ejecutar pruebas
python -m pytest -v

# 9. Ver ayuda
python main.py --help

# 10. Ejecutar una prueba pequeña desde cero
python main.py --reset --force --servicios 10 --dias 2

# 11. Ejecutar la corrida completa desde cero
python main.py --reset --force
```

---

## Licencia y uso

Este proyecto genera información sintética para fines académicos, de desarrollo, pruebas y análisis. No utiliza registros individuales reales de consumo eléctrico.
