# Asignación de zonas: generación paralela entre 6 personas

Documento interno de trabajo. Redactado el 21 de septiembre de 2026 sobre el repositorio
data-engine-for-energy-analysis. Actualizado en la rama `dev-mateo` con la territorialización
real de Toluca (pipeline CONEVAL GRS AGEB 2020) y la RD-06 reescrita del Entregable 1 v2.1.

El objetivo es simple: dividir la generación de los datos sintéticos de HyperDataSynthetic
entre 6 personas, asignando a cada una 4 de las 24 zonas de Toluca, para que cada
quien mejore sus reglas y produzca su bloque de registros sin pisar a los demás.

## 1. El punto de partida

Una precisión de escenario: el municipio real de Toluca (cabecera: Toluca de Lerdo) tiene
910.608 habitantes según el Censo 2020 del INEGI. No hay 24 municipios. Lo que hay son 24
zonas, definidas como sectores geográficos anclados a localidades y sectores reales del
municipio: un barrio, un fraccionamiento, una colonia. Cada zona es el nivel intermedio
de la cadena zona 1:N servicio 1:N medidor 1:N lectura, así que es la unidad natural de
reparto.

Reglas que condicionan el reparto:

- RD-06 (reescrita conforme al Entregable 1 v2.1): los nombres de zona y localidad *pueden*
  provenir de fuentes oficiales (CONEVAL, INEGI, IMPLAN Toluca). Lo que debe ser sintético
  y no replicar información real son las direcciones exactas, números de servicio, series
  de medidor e identificadores individuales. Cada integrante ancla sus 4 zonas a
  localidades reales del pipeline CONEVAL GRS AGEB 2020 sin solaparse.
  Localidades ya ancladas: P1 usa San Mateo Oxtotitlán, San José Guadalupe Otzacatipan,
  Sauces y San Nicolás Tolentino. P6 usa Toluca de Lerdo, San Pablo Autopan, San Cristóbal
  Huichochitlán y San Lorenzo Tepaltitlán. P3 referencia San Andrés Cuexcontitlán, Santiago
  Tlacotepec, Santa Ana Tlapaltitlán y Capultitlán. P2 usa San Andrés Mizquetenco.
- Los caracteres urbanos son 6: CENTRO, RESIDENCIAL_ALTA, RESIDENCIAL_MEDIA, POPULAR, MIXTA
  y PERIFERIA. Con 24 zonas, cada carácter aparece 4 veces.
- Cada zona declara superficie (km2) y factor socioeconomico entre 0.5 y 2.0, con el factor
  de la localidad real tomado del pipeline CONEVAL (Muy bajo 2.000, Bajo 1.625, Medio 1.250,
  Alto 0.875, Muy alto 0.500).
- Las 13 tablas y la canalización de 8 etapas del README no cambian.

## 2. Matriz de asignación

Seis personas, cuatro zonas cada una, con el rol secundario que exige la rúbrica
(obligatorio que cada integrante tenga más de un rol). Los nombres reales se completan
cuando el señor los entregue. Las localidades reales de anclaje ya definidas por cada
integrante en sus ramas se muestran en la columna "Ancla a localidad real".

| Persona | Zonas (id) | Ancla a localidad real (Toluca) | Carácter del ancla | Cuota servicios | Cuota lecturas | Rol secundario |
|---|---|---|---|---|---|---|
| P1, Mateo Jiménez Pérez | 1, 7, 13, 19 | 1 San Mateo Oxtotitlán · 7 San José Guadalupe Otzacatipan · 13 Sauces · 19 San Nicolás Tolentino | CENTRO (z1) | unos 833 | unos 1,800,000 | Líder de integración: une los 6 bloques y corre la corrida maestra |
| P2, David Nieto Ayala | 2, 8, 14, 20 | 2 San Andrés Mizquetenco | RESIDENCIAL_MEDIA | unos 833 | unos 1,800,000 | Perfiles de carga y calendario (1.296 perfiles, 90 días) |
| P3, Isabela Mosquera Fernández | 3, 9, 15, 21 | 3 San Andrés Cuexcontitlán · 9 Santiago Tlacotepec · 15 Santa Ana Tlapaltitlán · 21 Capultitlán | POPULAR (z3) | unos 833 | unos 1,800,000 | Reglas maestras y anomalías: maestro de Rules.json, sorteo de eventos |
| P4, Aalan Kalid Ruiz Colin | 4, 10, 16, 22 | por definir (ancla Fracc. Villas de Ocoyotenco) | RESIDENCIAL_ALTA | unos 833 | unos 1,800,000 | Persistencia: esquema de 13 tablas, inserción por lotes, checkpoints |
| P5, Sergio Martínez Blas | 5, 11, 17, 23 | por definir (ancla Colonia Nexpahuacán Norte) | MIXTA | unos 833 | unos 1,800,000 | Validación de integridad: conteos, claves, energías no negativas |
| P6, Ramiro Vega Meza | 6, 12, 18, 24 | 6 Toluca de Lerdo · 12 San Pablo Autopan · 18 San Cristóbal Huichochitlán · 24 San Lorenzo Tepaltitlán | CENTRO (z6) | unos 833 | unos 1,800,000 | Reproducibilidad y documentación: diff de corridas, guía |

Las cuotas son orientativas. El reparto fino de los 5.000 servicios entre las 24 zonas
depende de la superficie y del carácter de cada zona (una zona popular es más densa que una
residencial alta) y lo define cada dueño en sus reglas. La suma de los seis bloques debe
cuadrar con los totales oficiales: 5.000 servicios, 5.260 medidores, 10.800.000 lecturas,
unos 16.800 eventos, unas 12.900 alertas y 15.000 recibos.

Cada persona ancla sus 4 zonas a localidades reales del municipio de Toluca siguiendo la
RD-06 reescrita, sin repetir localidades ya tomadas por compañeros. En cada bloque deben
convivir 4 caracteres urbanos distintos, procurando una mezcla parecida entre personas para
que el trabajo sea homogéneo. La derivación de superficies se hace con las densidades del
IMPLAN Toluca y el factor socioeconómico, con el factor CONEVAL de la localidad.

## 3. Semillas y reproducibilidad

Dos corridas con la misma semilla y la misma versión de reglas deben dar resultados
idénticos. Con 6 personas generando en paralelo eso exige una regla de oro:

- La corrida oficial fija una semilla raiz, guardada en corrida_generacion.
- De la raiz se derivan 24 semillas por zona, de forma determinística, por ejemplo
  `semilla_zona = hash(f"{semilla_raiz}-z{id_zona}")` truncada a 32 bits.
- Cada persona usa la semilla de cada una de sus zonas. Así, aunque los bloques se
  generen en equipos distintos y en orden distinto, la unión de todos produce exactamente
  el mismo dataset que una corrida global.

Si alguien cambia una regla de una zona, sube la versión semver de Rules.json. Ese punto
no admite relajación.

## 4. Estructura nueva en el repositorio

```
data-engine-for-energy-analysis/
+-- Assignment/
|   +-- ASIGNACION_24_ZONAS.md        (este documento)
+-- Generation/
    +-- Zonas/
        +-- README.md                 (instrucciones del flujo por persona)
        +-- reglas_P1.json            (plantilla P1: zonas 1, 7, 13, 19)
        +-- reglas_P2.json            (plantilla P2: zonas 2, 8, 14, 20)
        +-- reglas_P3.json            (plantilla P3: zonas 3, 9, 15, 21)
        +-- reglas_P4.json            (plantilla P4: zonas 4, 10, 16, 22)
        +-- reglas_P5.json            (plantilla P5: zonas 5, 11, 17, 23)
        +-- reglas_P6.json            (plantilla P6: zonas 6, 12, 18, 24)
```

Las plantillas no rompen los scripts existentes: Profile_Gen.py sigue leyendo
Rules/Rules.json y Test/Testing_data/Tipo_servicio.json. Cada dueño trabaja su plantilla y
propone la integración; el maestro de reglas (P3) la valida y la sube a Rules.json maestro
con versión nueva.

Las salidas (Inserciones/, Conexión/, Test/, Generation/Resultados/) siguen fuera de git,
como manda el .gitignore. Ahí vive lo pesado, nunca en el repositorio.

## 5. Flujo por persona, semana a semana

Alineado al Plan de Desarrollo del 21 de septiembre al 28 de noviembre de 2026.

| Semana | Foco de cada persona | Hito |
|---|---|---|
| S1, 21-27 sep | Leer este documento y el README. Validar Profile_Gen.py con sus zonas. Componer los 3 nombres de zona pendientes | Criterios aceptados por el equipo |
| S2, 28 sep-4 oct | Completar reglas_Pn.json: mezcla de servicios, superficie y factor socioeconomico de sus 4 zonas | Primera inserción por zona |
| S3, 5-11 oct | Padrón de sus servicios y medidores; sorteo de eventos de sus zonas según tasas | Submuestra de 500 medidores de punta a punta |
| S4, 12-18 oct | Lecturas por lotes de sus zonas con reanudación | Pipeline de lecturas estable por zona |
| S5, 19-25 oct | Corrida completa de su bloque (unos 1,8 millones de lecturas) y medición | Bloque propio terminado |
| S6, 26 oct-1 nov | Vigilancia y facturación de sus zonas | Tablas de hechos de su bloque completas |
| S7, 2-8 nov | Entregar bloque a P1. Prueba de reproducibilidad: dos corridas de su zona, diff vacío | H3: validación aprobada |
| S8, 9-15 nov | Apoyo a datamart y dashboards con sus zonas | H4: BI listo |
| S9, 16-22 nov | Documentar sus decisiones de reglas | H5: documentación lista |
| S10, 23-28 nov | Ensayo y entrega final | H6: entrega del 28 de noviembre |

## 6. Entregables por persona

- reglas_Pn.json completado y validado contra el esquema de las 13 tablas.
- Bloque de INSERTs por zona, en Inserciones/ (fuera de git).
- Reporte de corrida con conteos por tabla de su bloque.
- Certificación de las pruebas T2, T3 y T5 sobre sus zonas.

## 7. Reglas de convivencia

- Cada quien toca solo sus archivos y sus ids de zona.
- Ninguna regla ajena se modifica sin avisar al dueño y al maestro.
- Cualquier cambio de reglas sube semver.
- Nada de credenciales ni resultados en el repositorio.

## 8. Pendientes

- Anclaje de las zonas pendientes: P4 (4, 10, 16, 22) y P5 (5, 11, 17, 23) aún no fijan
  localidades reales; P2 (8, 14, 20) y P3 (sin ancla) completan el resto. P1 y P6 ya
  tienen sus 4 localidades ancladas.
- Revisión y visto bueno del señor sobre esta asignación.
- Decidir la herramienta de gestión de tickets: Trello (en uso) o Jira, y aplicar la
  política de ramas del equipo (una rama por ticket, main protegida) a este repositorio.