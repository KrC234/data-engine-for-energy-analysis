# **data-engine-for-energy-analysis**

# Objetivo 
El objetivo del presente modulo es llevar a cabo la generación de datos sintéticos, así cómo la inserción de registros en la base de datos, mediante reglas de comportamiento y el uso de semillas para generar datos lo más cercanos a la realidad. 

# Análisis del Problema 

## Escenario 
El Valle de Nexpahuacán es una ciudad ficticia de alrededor 400,000 habitantes. 
El municipio en conjunto con la empresa que suministra electricidad, puso en marcha un programa piloto de medición inteligente. 
Para ello seleccionaron 5,000 puntos de consumo para instalar medidores capaces de transmitir sus lecturas automáticamente, hora tras hora,hacia un centro de monitoreo. 
El sistema no monitorea a toda la ciudad, monitorea una muestra representativa de ella. 
De los 5,000 puntos la gran mayoría, cerca de cuatro de cada 5, son viviendas particulares. Mientras que el resto se reparte entre comercios pequeños, edificios públicos como escuelas y clínicas, infraestructura de servicios y elementos de vía pública. 

## Concepto central: dos energías por lectura
Cada lectura horaria almacena dos cantidades de energía, no una:
+	**Energía reportada:** el número que salió del aparato y llegó al centro de monitoreo, tal cual, sin corrección alguna. Es lo único que un sistema real conocería.
+	**Energía real:** la energía que efectivamente circuló durante esa hora, con independencia de si el medidor la reportó bien, la reportó mal o no la reportó en absoluto. Es la verdad del mundo simulado.

En condiciones normales ambas cantidades coinciden. Cuando ocurre una anomalía se separan, y la forma en que se separan identifica el tipo de anomalía sin ambigüedad alguna.

Gracias a este tipo de análisis se pueden determinar escenarios como los siguientes: 
+ **Operación Normal:** El valor muestra un comportamiento basado en la curva de carga, reportando valores iguales en ambos registros. 
+ **Perdida de comunicación**: La energía real reporta que se consumió mientras que la reportada mantiene valores nulos. 
+ **Medidor congelado o  Averiado**: Se consume la energía normal, mientras que el medidor reporta un 0 constante (hora tras hora).
+ **Manipulación(Fraude)**: Se consume una gran cantidad de energía mientras que se reporta una fracción del valor real. 
+ **Pico de demanda**: Valor por arriba de lo habitual, los registros son iguales. 
+ **Consumo legitamente bajo**: Valor bajo en periodos esperados. 

## Concepto fundamental de modelado: curva de carga 
El concepto físico que sostiene toda la generación es la _curva de carga_, que refiere a la forma en que el consumo de un punto varía a lo largo del día.

Por ejemplo: 
Una vivienda consume poco durante la madrugada, algo más por la mañana y alcanza su máximo por la noche. Un mercado municipal presenta la forma opuesta: arranca temprano, culmina a media mañana y prácticamente se apaga de noche. Un circuito de alumbrado público invierte por completo el patrón: consume solo cuando no hay luz solar.

Este tipo de comportamiento define que es necesario hacer el monitoreo por hora y el hecho de que la curva característica debe ser un parámetro almacenado del sistema. 

> Existen tres modificadores adicionales sobre la curva,  que el generador aplica de manera multiplicativa: el tipo de día, el carácter socioeconómico de la zona y la estacionalidad.

## Anomalías y Alertas



# Modelado 

## Parámetros del escenario
Las consideraciones del modelo propuesto son las siguientes: 

+ **Puntos de consumo**: 5000
+ **Zonas de la ciudad**: 24 
+ **Tipos de punto de consumo**: 18 
+ **Clasificaciones tarifarias**: 7
+ **Frecuencia de lectura**: 1 por hora (24 al día)
+ **Periodo de observación**: 90 días
+ **Ciclo de facturación**: Mensual para todos los servicios
+ **Tipos de anomalía**: 7 


## Requisitos generales
De los requisitos funcionales y no funcionales del proyecto, se rescatan los más primordiales en relación a la generación de datos sinteticos. 

+ Generar territorio de la ciudad siguiendo reglas de composición propias, generar el padrón de puntos de consumo, instalación de los medidores sobre puntos de consumo. 
+ Generar una lectura por medidor y por hora durante los 90 días del periodo, incluso cuando la transmisión falle.
+ Calcular, para cada lectura, la energía real a partir de la curva de carga del tipo de servicio, el tipo de día, el factor de zona, la estacionalidad y un componente aleatorio.
+ Inyectar anomalías, derivar la energía real aplicando el efecto de la anomalía y simular la capa de vigilancia.
+ Emitir recibos mensuales para cada punto de consumo.
+ Registrar los parametros de cada ejecución. 
+ Reproducibilidad: dos ejecuciones con la misma semilla y la misma versión de reglas deben producir resultados idénticos.
+ Tiempo de generación: la corrida completa debe completarse en un equipo personal en un plazo razonable, con escritura por lotes.
## Arquitectura del generador y canalización de ocho etapas
La generación se ejecuta como una canalización de ocho etapas, cada una de las cuales consume lo producido por las anteriores. 

+ Registro de la corrida: Semilla, versión de reglas, huella de la configuración, alcance temporal
+ Catálogos: Zonas, tarifas, tipos de servicio, tipos de anomalía
+ Parámetros temporales: Calendario de 90 días con tipo de día y temperatura; perfiles de carga horaria
+ Padrón: Puntos de consumo con zona, tipo y tarifa; medidores con marca, instalación y calidad de comunicación. 
+ Anomalías: Sucesos con tipo, medidor, inicio, fin e intensidad, sorteados según las tasas declaradas
+ Lecturas: Una fila por medidor y hora, con energía real y energía reportada
+ Vigilancia:Alertas emitidas, incluidas omisiones y falsas alarmas
+ Facturación: Un recibo mensual por punto de consumo, con contador inicial y final

> Dos observaciones sobre la ejecución. La primera es que en la etapa de lecturas se escribe por lotes para que la carga pueda reanudarse si algo se interrumpe a la mitad, y para que la memoria del equipo no tenga que sostener diez millones de filas simultáneamente. La segunda es que las anomalías (E4) se sortean antes de generar las lecturas y no durante. 
## Modelado de la Base: Tablas 
El modelado de la base de datos propone las siguientes tablas, estás se encuentran clasificadas en base al uso de los datos en el sistema. 

|Familia|¿Qué representa?| Tablas|
|---|---|---|
|Catálogos|Los conjuntos cerrados de categorías que el sistema reconoce|zona, tarifa, tipo_servicio, tipo_evento|
|Parámetros|Las reglas con las que se generó y se interpreta el resto de la información|perfil_carga_horaria,calendario, corrida_generacion|
|Maestras|El inventario de lo que existe físicamente en la ciudad|servicio, medidor|
|Hechos|Lo que ocurre en el tiempo: mediciones, anomalías alertas, recibos| lectura, evento, alerta, periodo_facturacion|

> Para más información consultar documento del modelado de base de datos. 

