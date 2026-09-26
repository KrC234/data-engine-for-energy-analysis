/*
===============================================================================
HYPERDATASYNTHETIC - DIAGNOSTICO DE NULOS Y VIGENCIAS
Proyecto: Ramiro Vega Meza
Motor: PostgreSQL
Compatible con: pgAdmin Query Tool
===============================================================================

OBJETIVO
--------
1. Detectar valores NULL en campos obligatorios.
2. Diferenciar NULL legítimos de NULL incorrectos.
3. Detectar eventos creados antes de instalar el medidor.
4. Detectar eventos creados después de retirar el medidor.
5. Detectar eventos que comienzan vigentes, pero terminan después del retiro.
6. Detectar alertas generadas fuera de la vigencia del medidor.

IMPORTANTE
----------
Este script no modifica ningún dato.
Solo utiliza consultas SELECT.
===============================================================================
*/


-- ============================================================================
-- 1. RESUMEN GENERAL DE NULOS OBLIGATORIOS
-- ============================================================================

SELECT
    'SERVICIOS' AS categoria,
    COUNT(*) AS registros_con_error,
    'Campos obligatorios NULL' AS problema
FROM energia.servicio
WHERE rpu IS NULL
   OR id_zona IS NULL
   OR id_tipo_servicio IS NULL
   OR id_tarifa IS NULL
   OR nombre IS NULL
   OR latitud IS NULL
   OR longitud IS NULL
   OR carga_contratada_kw IS NULL
   OR tiene_solar IS NULL

UNION ALL

SELECT
    'MEDIDORES',
    COUNT(*),
    'Campos obligatorios NULL'
FROM energia.medidor
WHERE id_servicio IS NULL
   OR numero_serie IS NULL
   OR fecha_instalacion IS NULL
   OR multiplicador IS NULL
   OR calidad_enlace IS NULL

UNION ALL

SELECT
    'EVENTOS',
    COUNT(*),
    'Campos obligatorios NULL'
FROM energia.evento
WHERE id_medidor IS NULL
   OR id_tipo_evento IS NULL
   OR ts_inicio IS NULL
   OR ts_fin IS NULL
   OR kwh_desviados IS NULL

UNION ALL

SELECT
    'LECTURAS',
    COUNT(*),
    'Campos obligatorios NULL'
FROM energia.lectura
WHERE id_medidor IS NULL
   OR ts IS NULL
   OR consumo_real_kwh IS NULL

UNION ALL

SELECT
    'ALERTAS',
    COUNT(*),
    'Campos obligatorios NULL'
FROM energia.alerta
WHERE id_medidor IS NULL
   OR id_tipo_evento IS NULL
   OR ts_generacion IS NULL
   OR prioridad IS NULL

UNION ALL

SELECT
    'FACTURACION',
    COUNT(*),
    'Campos obligatorios NULL'
FROM energia.periodo_facturacion
WHERE id_servicio IS NULL
   OR folio IS NULL
   OR fecha_inicio IS NULL
   OR fecha_fin IS NULL
   OR id_tarifa_aplicada IS NULL
   OR registro_inicial_kwh IS NULL
   OR registro_final_kwh IS NULL
   OR consumo_real_kwh IS NULL
   OR clasificacion_dac IS NULL

ORDER BY categoria;


-- ============================================================================
-- 2. SERVICIOS CON CAMPOS OBLIGATORIOS NULL
-- ============================================================================

SELECT
    id_servicio,
    rpu,
    id_zona,
    id_tipo_servicio,
    id_tarifa,
    nombre,
    latitud,
    longitud,
    ocupacion_estimada,
    carga_contratada_kw,
    tiene_solar,
    CASE
        WHEN rpu IS NULL THEN 'RPU NULL'
        WHEN id_zona IS NULL THEN 'ZONA NULL'
        WHEN id_tipo_servicio IS NULL THEN 'TIPO_SERVICIO NULL'
        WHEN id_tarifa IS NULL THEN 'TARIFA NULL'
        WHEN nombre IS NULL THEN 'NOMBRE NULL'
        WHEN latitud IS NULL THEN 'LATITUD NULL'
        WHEN longitud IS NULL THEN 'LONGITUD NULL'
        WHEN carga_contratada_kw IS NULL THEN 'CARGA_CONTRATADA NULL'
        WHEN tiene_solar IS NULL THEN 'TIENE_SOLAR NULL'
        ELSE 'OTRO'
    END AS primer_error_detectado
FROM energia.servicio
WHERE rpu IS NULL
   OR id_zona IS NULL
   OR id_tipo_servicio IS NULL
   OR id_tarifa IS NULL
   OR nombre IS NULL
   OR latitud IS NULL
   OR longitud IS NULL
   OR carga_contratada_kw IS NULL
   OR tiene_solar IS NULL
ORDER BY id_servicio;


-- ============================================================================
-- 3. MEDIDORES CON CAMPOS OBLIGATORIOS NULL
-- ============================================================================

SELECT
    id_medidor,
    id_servicio,
    numero_serie,
    fecha_instalacion,
    fecha_retiro,
    multiplicador,
    calidad_enlace,
    CASE
        WHEN id_servicio IS NULL THEN 'SERVICIO NULL'
        WHEN numero_serie IS NULL THEN 'NUMERO_SERIE NULL'
        WHEN fecha_instalacion IS NULL THEN 'FECHA_INSTALACION NULL'
        WHEN multiplicador IS NULL THEN 'MULTIPLICADOR NULL'
        WHEN calidad_enlace IS NULL THEN 'CALIDAD_ENLACE NULL'
        ELSE 'OTRO'
    END AS primer_error_detectado
FROM energia.medidor
WHERE id_servicio IS NULL
   OR numero_serie IS NULL
   OR fecha_instalacion IS NULL
   OR multiplicador IS NULL
   OR calidad_enlace IS NULL
ORDER BY id_medidor;


-- ============================================================================
-- 4. EVENTOS CON CAMPOS OBLIGATORIOS NULL
-- ============================================================================

SELECT
    id_evento,
    id_medidor,
    id_tipo_evento,
    ts_inicio,
    ts_fin,
    intensidad,
    kwh_desviados,
    CASE
        WHEN id_medidor IS NULL THEN 'MEDIDOR NULL'
        WHEN id_tipo_evento IS NULL THEN 'TIPO_EVENTO NULL'
        WHEN ts_inicio IS NULL THEN 'INICIO NULL'
        WHEN ts_fin IS NULL THEN 'FIN NULL'
        WHEN kwh_desviados IS NULL THEN 'KWH_DESVIADOS NULL'
        ELSE 'OTRO'
    END AS primer_error_detectado
FROM energia.evento
WHERE id_medidor IS NULL
   OR id_tipo_evento IS NULL
   OR ts_inicio IS NULL
   OR ts_fin IS NULL
   OR kwh_desviados IS NULL
ORDER BY id_evento;


-- ============================================================================
-- 5. INTENSIDAD NULL INCORRECTA SEGUN EL TIPO DE EVENTO
-- ============================================================================

SELECT
    e.id_evento,
    e.id_medidor,
    e.id_tipo_evento,
    te.clave,
    te.efecto,
    e.intensidad,
    te.intensidad_min,
    te.intensidad_max,
    CASE
        WHEN UPPER(te.efecto) IN ('INCREMENTO', 'REDUCCION')
             AND e.intensidad IS NULL
            THEN 'FALTA_INTENSIDAD'

        WHEN UPPER(te.efecto) IN ('CONGELAMIENTO', 'NULIFICACION')
             AND e.intensidad IS NOT NULL
            THEN 'INTENSIDAD_NO_DEBE_EXISTIR'

        WHEN e.intensidad IS NOT NULL
             AND e.intensidad < te.intensidad_min
            THEN 'INTENSIDAD_MENOR_AL_MINIMO'

        WHEN e.intensidad IS NOT NULL
             AND e.intensidad > te.intensidad_max
            THEN 'INTENSIDAD_MAYOR_AL_MAXIMO'

        ELSE 'OTRO'
    END AS problema
FROM energia.evento e
JOIN energia.tipo_evento te
  ON te.id_tipo_evento = e.id_tipo_evento
WHERE (
        UPPER(te.efecto) IN ('INCREMENTO', 'REDUCCION')
        AND e.intensidad IS NULL
      )
   OR (
        UPPER(te.efecto) IN ('CONGELAMIENTO', 'NULIFICACION')
        AND e.intensidad IS NOT NULL
      )
   OR (
        e.intensidad IS NOT NULL
        AND e.intensidad < te.intensidad_min
      )
   OR (
        e.intensidad IS NOT NULL
        AND e.intensidad > te.intensidad_max
      )
ORDER BY e.id_evento;


-- ============================================================================
-- 6. RESUMEN DE EVENTOS FUERA DE VIGENCIA
-- ============================================================================

SELECT
    CASE
        WHEN e.ts_inicio < m.fecha_instalacion::timestamp
            THEN 'INICIA_ANTES_DE_INSTALACION'

        WHEN m.fecha_retiro IS NOT NULL
             AND e.ts_inicio >= m.fecha_retiro::timestamp
            THEN 'INICIA_DESPUES_DEL_RETIRO'

        WHEN m.fecha_retiro IS NOT NULL
             AND e.ts_fin > m.fecha_retiro::timestamp
            THEN 'TERMINA_DESPUES_DEL_RETIRO'

        ELSE 'OTRO'
    END AS tipo_problema,
    COUNT(*) AS cantidad
FROM energia.evento e
JOIN energia.medidor m
  ON m.id_medidor = e.id_medidor
WHERE e.ts_inicio < m.fecha_instalacion::timestamp
   OR (
        m.fecha_retiro IS NOT NULL
        AND e.ts_fin > m.fecha_retiro::timestamp
      )
GROUP BY 1
ORDER BY cantidad DESC;


-- ============================================================================
-- 7. DETALLE DE EVENTOS FUERA DE VIGENCIA
-- ============================================================================

SELECT
    e.id_evento,
    e.id_medidor,
    m.id_servicio,
    m.numero_serie,
    m.fecha_instalacion,
    m.fecha_retiro,
    e.ts_inicio,
    e.ts_fin,
    e.ts_inicio - m.fecha_instalacion::timestamp
        AS diferencia_con_instalacion,
    CASE
        WHEN e.ts_inicio < m.fecha_instalacion::timestamp
            THEN 'INICIA_ANTES_DE_INSTALACION'

        WHEN m.fecha_retiro IS NOT NULL
             AND e.ts_inicio >= m.fecha_retiro::timestamp
            THEN 'INICIA_DESPUES_DEL_RETIRO'

        WHEN m.fecha_retiro IS NOT NULL
             AND e.ts_fin > m.fecha_retiro::timestamp
            THEN 'TERMINA_DESPUES_DEL_RETIRO'

        ELSE 'OTRO'
    END AS problema
FROM energia.evento e
JOIN energia.medidor m
  ON m.id_medidor = e.id_medidor
WHERE e.ts_inicio < m.fecha_instalacion::timestamp
   OR (
        m.fecha_retiro IS NOT NULL
        AND e.ts_fin > m.fecha_retiro::timestamp
      )
ORDER BY
    problema,
    m.id_servicio,
    e.ts_inicio;


-- ============================================================================
-- 8. CANTIDAD DE MEDIDORES Y SERVICIOS AFECTADOS
-- ============================================================================

SELECT
    COUNT(*) AS eventos_invalidos,
    COUNT(DISTINCT e.id_medidor) AS medidores_afectados,
    COUNT(DISTINCT m.id_servicio) AS servicios_afectados
FROM energia.evento e
JOIN energia.medidor m
  ON m.id_medidor = e.id_medidor
WHERE e.ts_inicio < m.fecha_instalacion::timestamp
   OR (
        m.fecha_retiro IS NOT NULL
        AND e.ts_fin > m.fecha_retiro::timestamp
      );


-- ============================================================================
-- 9. EVENTOS INVÁLIDOS EN SERVICIOS CON REEMPLAZO
-- ============================================================================

WITH eventos_invalidos AS (
    SELECT
        e.id_evento,
        e.id_medidor,
        m.id_servicio
    FROM energia.evento e
    JOIN energia.medidor m
      ON m.id_medidor = e.id_medidor
    WHERE e.ts_inicio < m.fecha_instalacion::timestamp
       OR (
            m.fecha_retiro IS NOT NULL
            AND e.ts_fin > m.fecha_retiro::timestamp
          )
),
servicios_reemplazados AS (
    SELECT
        id_servicio
    FROM energia.medidor
    GROUP BY id_servicio
    HAVING COUNT(*) > 1
)
SELECT
    COUNT(*) AS eventos_invalidos,

    COUNT(*) FILTER (
        WHERE sr.id_servicio IS NOT NULL
    ) AS en_servicios_reemplazados,

    COUNT(*) FILTER (
        WHERE sr.id_servicio IS NULL
    ) AS en_servicios_sin_reemplazo,

    COUNT(DISTINCT ei.id_servicio) AS servicios_afectados
FROM eventos_invalidos ei
LEFT JOIN servicios_reemplazados sr
  ON sr.id_servicio = ei.id_servicio;


-- ============================================================================
-- 10. BUSCAR EL MEDIDOR QUE REALMENTE CORRESPONDIA AL EVENTO
-- ============================================================================

WITH eventos_invalidos AS (
    SELECT
        e.id_evento,
        e.id_medidor AS medidor_asignado,
        e.id_tipo_evento,
        e.ts_inicio,
        e.ts_fin,
        m.id_servicio,
        m.fecha_instalacion AS instalacion_asignada,
        m.fecha_retiro AS retiro_asignado
    FROM energia.evento e
    JOIN energia.medidor m
      ON m.id_medidor = e.id_medidor
    WHERE e.ts_inicio < m.fecha_instalacion::timestamp
       OR (
            m.fecha_retiro IS NOT NULL
            AND e.ts_fin > m.fecha_retiro::timestamp
          )
)
SELECT
    ei.id_evento,
    ei.id_servicio,
    ei.medidor_asignado,
    correcto.id_medidor AS medidor_que_correspondia,
    ei.ts_inicio,
    ei.ts_fin,
    ei.instalacion_asignada,
    ei.retiro_asignado,
    correcto.fecha_instalacion AS instalacion_correcta,
    correcto.fecha_retiro AS retiro_correcto,
    CASE
        WHEN correcto.id_medidor IS NOT NULL
            THEN 'EVENTO_ASIGNADO_AL_MEDIDOR_INCORRECTO'
        ELSE 'NO_EXISTE_OTRO_MEDIDOR_VALIDO'
    END AS diagnostico
FROM eventos_invalidos ei
LEFT JOIN energia.medidor correcto
  ON correcto.id_servicio = ei.id_servicio
 AND correcto.id_medidor <> ei.medidor_asignado
 AND ei.ts_inicio >= correcto.fecha_instalacion::timestamp
 AND (
      correcto.fecha_retiro IS NULL
      OR ei.ts_fin <= correcto.fecha_retiro::timestamp
 )
ORDER BY
    ei.id_servicio,
    ei.ts_inicio;


-- ============================================================================
-- 11. LECTURAS CON CAMPOS OBLIGATORIOS NULL
-- ============================================================================

SELECT
    id_medidor,
    ts,
    consumo_kwh,
    consumo_real_kwh,
    id_evento,
    CASE
        WHEN id_medidor IS NULL THEN 'MEDIDOR NULL'
        WHEN ts IS NULL THEN 'FECHA_HORA NULL'
        WHEN consumo_real_kwh IS NULL THEN 'CONSUMO_REAL NULL'
        ELSE 'OTRO'
    END AS problema
FROM energia.lectura
WHERE id_medidor IS NULL
   OR ts IS NULL
   OR consumo_real_kwh IS NULL
ORDER BY ts, id_medidor;


-- ============================================================================
-- 12. CONSUMO_KWH NULL SIN NULIFICACION VALIDA
-- ============================================================================

SELECT
    l.id_medidor,
    l.ts,
    l.consumo_kwh,
    l.consumo_real_kwh,
    l.id_evento,
    e.ts_inicio AS inicio_evento,
    e.ts_fin AS fin_evento,
    te.efecto,
    CASE
        WHEN l.id_evento IS NULL
            THEN 'LECTURA_NULL_SIN_EVENTO'

        WHEN e.id_evento IS NULL
            THEN 'EVENTO_REFERENCIADO_NO_EXISTE'

        WHEN te.id_tipo_evento IS NULL
            THEN 'TIPO_EVENTO_NO_EXISTE'

        WHEN UPPER(te.efecto) <> 'NULIFICACION'
            THEN 'NULL_EN_EVENTO_QUE_NO_ES_NULIFICACION'

        WHEN l.ts < e.ts_inicio
            THEN 'LECTURA_ANTES_DEL_EVENTO'

        WHEN l.ts >= e.ts_fin
            THEN 'LECTURA_DESPUES_DEL_EVENTO'

        WHEN l.consumo_real_kwh IS NULL
            THEN 'CONSUMO_REAL_TAMBIEN_ES_NULL'

        ELSE 'OTRO'
    END AS problema
FROM energia.lectura l
LEFT JOIN energia.evento e
  ON e.id_evento = l.id_evento
LEFT JOIN energia.tipo_evento te
  ON te.id_tipo_evento = e.id_tipo_evento
WHERE l.consumo_kwh IS NULL
  AND (
       l.id_evento IS NULL
       OR e.id_evento IS NULL
       OR te.id_tipo_evento IS NULL
       OR UPPER(te.efecto) <> 'NULIFICACION'
       OR l.ts < e.ts_inicio
       OR l.ts >= e.ts_fin
       OR l.consumo_real_kwh IS NULL
  )
ORDER BY l.ts, l.id_medidor;


-- ============================================================================
-- 13. ALERTAS CON CAMPOS OBLIGATORIOS NULL
-- ============================================================================

SELECT
    id_alerta,
    id_evento,
    id_medidor,
    id_tipo_evento,
    ts_generacion,
    prioridad,
    ts_cierre,
    resultado,
    CASE
        WHEN id_medidor IS NULL THEN 'MEDIDOR NULL'
        WHEN id_tipo_evento IS NULL THEN 'TIPO_EVENTO NULL'
        WHEN ts_generacion IS NULL THEN 'FECHA_GENERACION NULL'
        WHEN prioridad IS NULL THEN 'PRIORIDAD NULL'
        ELSE 'OTRO'
    END AS problema
FROM energia.alerta
WHERE id_medidor IS NULL
   OR id_tipo_evento IS NULL
   OR ts_generacion IS NULL
   OR prioridad IS NULL
ORDER BY id_alerta;


-- ============================================================================
-- 14. ALERTAS CON CIERRE INCONSISTENTE
-- ============================================================================

SELECT
    id_alerta,
    id_evento,
    id_medidor,
    ts_generacion,
    ts_cierre,
    resultado,
    CASE
        WHEN ts_cierre IS NULL AND resultado IS NOT NULL
            THEN 'RESULTADO_SIN_FECHA_CIERRE'

        WHEN ts_cierre IS NOT NULL AND resultado IS NULL
            THEN 'FECHA_CIERRE_SIN_RESULTADO'

        WHEN ts_cierre IS NOT NULL
             AND ts_cierre < ts_generacion
            THEN 'CIERRE_ANTES_DE_GENERACION'

        ELSE 'OTRO'
    END AS problema
FROM energia.alerta
WHERE (ts_cierre IS NULL AND resultado IS NOT NULL)
   OR (ts_cierre IS NOT NULL AND resultado IS NULL)
   OR (
        ts_cierre IS NOT NULL
        AND ts_cierre < ts_generacion
      )
ORDER BY id_alerta;


-- ============================================================================
-- 15. RESUMEN DE ALERTAS FUERA DE VIGENCIA
-- ============================================================================

SELECT
    CASE
        WHEN a.ts_generacion < m.fecha_instalacion::timestamp
            THEN 'GENERADA_ANTES_DE_INSTALACION'

        WHEN m.fecha_retiro IS NOT NULL
             AND a.ts_generacion >= m.fecha_retiro::timestamp
            THEN 'GENERADA_DESPUES_DEL_RETIRO'

        ELSE 'OTRO'
    END AS tipo_problema,
    COUNT(*) AS cantidad
FROM energia.alerta a
JOIN energia.medidor m
  ON m.id_medidor = a.id_medidor
WHERE a.ts_generacion < m.fecha_instalacion::timestamp
   OR (
        m.fecha_retiro IS NOT NULL
        AND a.ts_generacion >= m.fecha_retiro::timestamp
      )
GROUP BY 1
ORDER BY cantidad DESC;


-- ============================================================================
-- 16. DETALLE DE ALERTAS FUERA DE VIGENCIA
-- ============================================================================

SELECT
    a.id_alerta,
    a.id_evento,
    a.id_medidor,
    m.id_servicio,
    m.numero_serie,
    m.fecha_instalacion,
    m.fecha_retiro,
    a.ts_generacion,
    a.prioridad,
    a.ts_cierre,
    a.resultado,
    CASE
        WHEN a.ts_generacion < m.fecha_instalacion::timestamp
            THEN 'GENERADA_ANTES_DE_INSTALACION'

        WHEN m.fecha_retiro IS NOT NULL
             AND a.ts_generacion >= m.fecha_retiro::timestamp
            THEN 'GENERADA_DESPUES_DEL_RETIRO'

        ELSE 'OTRO'
    END AS problema
FROM energia.alerta a
JOIN energia.medidor m
  ON m.id_medidor = a.id_medidor
WHERE a.ts_generacion < m.fecha_instalacion::timestamp
   OR (
        m.fecha_retiro IS NOT NULL
        AND a.ts_generacion >= m.fecha_retiro::timestamp
      )
ORDER BY
    problema,
    m.id_servicio,
    a.ts_generacion;


-- ============================================================================
-- 17. RELACION ENTRE EVENTOS INVALIDOS Y ALERTAS INVALIDAS
-- ============================================================================

WITH eventos_invalidos AS (
    SELECT
        e.id_evento
    FROM energia.evento e
    JOIN energia.medidor m
      ON m.id_medidor = e.id_medidor
    WHERE e.ts_inicio < m.fecha_instalacion::timestamp
       OR (
            m.fecha_retiro IS NOT NULL
            AND e.ts_fin > m.fecha_retiro::timestamp
          )
),
alertas_invalidas AS (
    SELECT
        a.id_alerta,
        a.id_evento
    FROM energia.alerta a
    JOIN energia.medidor m
      ON m.id_medidor = a.id_medidor
    WHERE a.ts_generacion < m.fecha_instalacion::timestamp
       OR (
            m.fecha_retiro IS NOT NULL
            AND a.ts_generacion >= m.fecha_retiro::timestamp
          )
)
SELECT
    (SELECT COUNT(*) FROM eventos_invalidos)
        AS eventos_fuera_vigencia,

    (SELECT COUNT(*) FROM alertas_invalidas)
        AS alertas_fuera_vigencia,

    (
        SELECT COUNT(*)
        FROM alertas_invalidas ai
        JOIN eventos_invalidos ei
          ON ei.id_evento = ai.id_evento
    ) AS alertas_de_eventos_invalidos,

    (
        SELECT COUNT(*)
        FROM alertas_invalidas ai
        LEFT JOIN eventos_invalidos ei
          ON ei.id_evento = ai.id_evento
        WHERE ei.id_evento IS NULL
    ) AS alertas_invalidas_sin_evento_invalido;


-- ============================================================================
-- 18. FACTURACION CON CAMPOS OBLIGATORIOS NULL
-- ============================================================================

SELECT
    id_periodo,
    id_servicio,
    folio,
    fecha_inicio,
    fecha_fin,
    id_tarifa_aplicada,
    registro_inicial_kwh,
    registro_final_kwh,
    consumo_real_kwh,
    clasificacion_dac,
    CASE
        WHEN id_servicio IS NULL THEN 'SERVICIO NULL'
        WHEN folio IS NULL THEN 'FOLIO NULL'
        WHEN fecha_inicio IS NULL THEN 'FECHA_INICIO NULL'
        WHEN fecha_fin IS NULL THEN 'FECHA_FIN NULL'
        WHEN id_tarifa_aplicada IS NULL THEN 'TARIFA_APLICADA NULL'
        WHEN registro_inicial_kwh IS NULL THEN 'REGISTRO_INICIAL NULL'
        WHEN registro_final_kwh IS NULL THEN 'REGISTRO_FINAL NULL'
        WHEN consumo_real_kwh IS NULL THEN 'CONSUMO_REAL NULL'
        WHEN clasificacion_dac IS NULL THEN 'CLASIFICACION_DAC NULL'
        ELSE 'OTRO'
    END AS problema
FROM energia.periodo_facturacion
WHERE id_servicio IS NULL
   OR folio IS NULL
   OR fecha_inicio IS NULL
   OR fecha_fin IS NULL
   OR id_tarifa_aplicada IS NULL
   OR registro_inicial_kwh IS NULL
   OR registro_final_kwh IS NULL
   OR consumo_real_kwh IS NULL
   OR clasificacion_dac IS NULL
ORDER BY id_periodo;


-- ============================================================================
-- 19. NULL LEGITIMOS, SOLO INFORMATIVO
-- ============================================================================

SELECT
    'MEDIDORES_ACTIVOS_SIN_FECHA_RETIRO' AS concepto,
    COUNT(*) AS cantidad,
    'PERMITIDO' AS estado
FROM energia.medidor
WHERE fecha_retiro IS NULL

UNION ALL

SELECT
    'LECTURAS_NORMALES_SIN_EVENTO',
    COUNT(*),
    'PERMITIDO'
FROM energia.lectura
WHERE id_evento IS NULL

UNION ALL

SELECT
    'LECTURAS_SIN_CONSUMO_REPORTADO',
    COUNT(*),
    'PERMITIDO SOLO CON NULIFICACION'
FROM energia.lectura
WHERE consumo_kwh IS NULL

UNION ALL

SELECT
    'ALERTAS_ABIERTAS',
    COUNT(*),
    'PERMITIDO'
FROM energia.alerta
WHERE ts_cierre IS NULL
  AND resultado IS NULL

UNION ALL

SELECT
    'EVENTOS_SIN_INTENSIDAD',
    COUNT(*),
    'PERMITIDO PARA CONGELAMIENTO Y NULIFICACION'
FROM energia.evento e
JOIN energia.tipo_evento te
  ON te.id_tipo_evento = e.id_tipo_evento
WHERE UPPER(te.efecto) IN ('CONGELAMIENTO', 'NULIFICACION')
  AND e.intensidad IS NULL

UNION ALL

SELECT
    'OCUPACION_NULL_NO_RESIDENCIAL',
    COUNT(*),
    'PERMITIDO'
FROM energia.servicio s
JOIN energia.tipo_servicio ts
  ON ts.id_tipo_servicio = s.id_tipo_servicio
WHERE UPPER(ts.categoria) <> 'RESIDENCIAL'
  AND s.ocupacion_estimada IS NULL;


-- ============================================================================
-- 20. RESUMEN FINAL DE LOS PROBLEMAS PRINCIPALES
-- ============================================================================

SELECT
    'SERVICIOS_CON_NULOS' AS validacion,
    COUNT(*) AS encontrados,
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END AS estado
FROM energia.servicio
WHERE rpu IS NULL
   OR id_zona IS NULL
   OR id_tipo_servicio IS NULL
   OR id_tarifa IS NULL
   OR nombre IS NULL
   OR latitud IS NULL
   OR longitud IS NULL
   OR carga_contratada_kw IS NULL
   OR tiene_solar IS NULL

UNION ALL

SELECT
    'MEDIDORES_CON_NULOS',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END
FROM energia.medidor
WHERE id_servicio IS NULL
   OR numero_serie IS NULL
   OR fecha_instalacion IS NULL
   OR multiplicador IS NULL
   OR calidad_enlace IS NULL

UNION ALL

SELECT
    'EVENTOS_CON_NULOS',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END
FROM energia.evento
WHERE id_medidor IS NULL
   OR id_tipo_evento IS NULL
   OR ts_inicio IS NULL
   OR ts_fin IS NULL
   OR kwh_desviados IS NULL

UNION ALL

SELECT
    'EVENTOS_FUERA_DE_VIGENCIA',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END
FROM energia.evento e
JOIN energia.medidor m
  ON m.id_medidor = e.id_medidor
WHERE e.ts_inicio < m.fecha_instalacion::timestamp
   OR (
        m.fecha_retiro IS NOT NULL
        AND e.ts_fin > m.fecha_retiro::timestamp
      )

UNION ALL

SELECT
    'LECTURAS_CON_NULOS_OBLIGATORIOS',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END
FROM energia.lectura
WHERE id_medidor IS NULL
   OR ts IS NULL
   OR consumo_real_kwh IS NULL

UNION ALL

SELECT
    'CONSUMOS_NULL_SIN_NULIFICACION',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END
FROM energia.lectura l
LEFT JOIN energia.evento e
  ON e.id_evento = l.id_evento
LEFT JOIN energia.tipo_evento te
  ON te.id_tipo_evento = e.id_tipo_evento
WHERE l.consumo_kwh IS NULL
  AND (
       l.id_evento IS NULL
       OR e.id_evento IS NULL
       OR UPPER(te.efecto) <> 'NULIFICACION'
       OR l.ts < e.ts_inicio
       OR l.ts >= e.ts_fin
       OR l.consumo_real_kwh IS NULL
  )

UNION ALL

SELECT
    'ALERTAS_CON_NULOS',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END
FROM energia.alerta
WHERE id_medidor IS NULL
   OR id_tipo_evento IS NULL
   OR ts_generacion IS NULL
   OR prioridad IS NULL

UNION ALL

SELECT
    'ALERTAS_FUERA_DE_VIGENCIA',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END
FROM energia.alerta a
JOIN energia.medidor m
  ON m.id_medidor = a.id_medidor
WHERE a.ts_generacion < m.fecha_instalacion::timestamp
   OR (
        m.fecha_retiro IS NOT NULL
        AND a.ts_generacion >= m.fecha_retiro::timestamp
      )

UNION ALL

SELECT
    'FACTURACION_CON_NULOS',
    COUNT(*),
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END
FROM energia.periodo_facturacion
WHERE id_servicio IS NULL
   OR folio IS NULL
   OR fecha_inicio IS NULL
   OR fecha_fin IS NULL
   OR id_tarifa_aplicada IS NULL
   OR registro_inicial_kwh IS NULL
   OR registro_final_kwh IS NULL
   OR consumo_real_kwh IS NULL
   OR clasificacion_dac IS NULL

ORDER BY validacion;