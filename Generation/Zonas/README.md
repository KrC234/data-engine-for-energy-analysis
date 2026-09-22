# Reglas por zona: cómo trabajar cada persona

Esta carpeta contiene la división del trabajo de generación: 24 zonas de Nexpahuacán
repartidas entre 6 personas, 4 zonas por persona. Cada persona edita únicamente su
archivo reglas_Pn.json.

## Referencias

- Reparto completo, cuotas y cronograma: Assignment/ASIGNACION_24_ZONAS.md
- Reglas maestro y versionado: Rules/Rules.json (el maestro de reglas, rol P3, integra)
- Escenario y modelo de datos: README.md en la raiz

## Qué hace cada persona

1. Abrir su plantilla reglas_Pn.json.
2. Componer los nombres de sus zonas sin ancla (regla RD-06: nada de "Zona 7" ni fuentes
   reales; raíces y terminaciones propias del equipo).
3. Ajustar para cada zona: superficie_km2, factor_socioeconomico (0.5 a 2.0), tipos de
   servicio previstos y cualquier matiz de curva o tasa que quiera proponer.
4. Derivar la semilla de cada zona desde la semilla raiz de la corrida oficial, con la
   fórmula documentada: semilla_zona = hash(f"{semilla_raiz}-z{id_zona}") truncada a 32 bits.
5. Proponer la integración al maestro de reglas (P3). Solo P3 sube cambios a Rules.json
   y solo con versión semver nueva.

## Reglas duras

- No se tocan los archivos de otra persona.
- Los scripts existentes no se ven afectados: Profile_Gen.py sigue usando
  Rules/Rules.json y Test/Testing_data/Tipo_servicio.json.
- Las salidas (Inserciones/, Conexión/, Test/, Generation/Resultados/) no se suben a git.
- Dos corridas con la misma semilla y reglas deben dar diff vacío. Si no, algo se está
  haciendo mal.