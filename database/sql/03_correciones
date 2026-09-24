-- =====================================================================
-- correcciones_post_restore.sql
-- HyperDataSynthetic
-- Base de datos: energia_hsd
-- Esquema: energia
-- Usuario de la aplicacion: equipo_hsd
--
-- OBJETIVO
-- -------
-- Ejecutar despues de restaurar un pg_dump para:
--
-- 1. Comprobar que existen la base, esquema, usuario y tablas.
-- 2. Corregir el autoincremento de energia.medidor.id_medidor.
-- 3. Corregir el tipo y la restriccion de calidad_enlace.
-- 4. Otorgar permisos al usuario equipo_hsd.
-- 5. Configurar permisos para objetos futuros.
-- 6. Sincronizar secuencias existentes.
-- 7. Ejecutar validaciones finales.
--
-- IMPORTANTE
-- ----------
-- Ejecutar conectado a energia_hsd como:
--
-- - postgres; o
-- - propietario del esquema energia y de sus tablas.
--
-- La limpieza de datos sinteticos se encuentra comentada al final.
-- No la descomentes si quieres conservar los datos restaurados.
-- =====================================================================


-- =====================================================================
-- 0. MOSTRAR CONTEXTO DE EJECUCION
-- =====================================================================

SELECT
    current_database() AS base_actual,
    current_user AS usuario_actual,
    current_schema() AS esquema_actual,
    version() AS version_postgresql;


-- =====================================================================
-- 1. COMPROBAR BASE DE DATOS
-- =====================================================================

DO $$
BEGIN
    IF current_database() <> 'energia_hsd' THEN
        RAISE EXCEPTION
            'Este script debe ejecutarse conectado a energia_hsd. Base actual: %',
            current_database();
    END IF;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 2. COMPROBAR USUARIO DE LA APLICACION
-- =====================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'equipo_hsd'
    ) THEN
        RAISE EXCEPTION
            'No existe el usuario equipo_hsd. Debes crearlo antes de continuar.';
    END IF;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 3. COMPROBAR ESQUEMA
-- =====================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.schemata
        WHERE schema_name = 'energia'
    ) THEN
        RAISE EXCEPTION
            'No existe el esquema energia. Restaura primero el pg_dump.';
    END IF;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 4. COMPROBAR TABLAS PRINCIPALES
-- =====================================================================

DO $$
DECLARE
    tabla_requerida TEXT;
    tablas_requeridas TEXT[] := ARRAY[
        'zona',
        'tarifa',
        'tipo_servicio',
        'tipo_evento',
        'perfil_carga_horaria',
        'calendario',
        'servicio',
        'medidor',
        'evento',
        'lectura',
        'alerta',
        'periodo_facturacion'
    ];
BEGIN
    FOREACH tabla_requerida IN ARRAY tablas_requeridas
    LOOP
        IF to_regclass(
            format('energia.%I', tabla_requerida)
        ) IS NULL THEN
            RAISE EXCEPTION
                'No existe la tabla energia.%. Restaura primero el esquema.',
                tabla_requerida;
        END IF;
    END LOOP;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 5. INICIAR TRANSACCION DE CORRECCIONES
-- =====================================================================

BEGIN;


-- =====================================================================
-- 6. CORREGIR energia.medidor.id_medidor
-- =====================================================================
--
-- Problema solucionado:
--
-- null value in column "id_medidor" violates not-null constraint
--
-- La columna debe generar automaticamente un identificador cuando
-- Python no proporciona id_medidor.
-- =====================================================================

DO $$
DECLARE
    columna_existe BOOLEAN;
    es_identity BOOLEAN;
    tipo_columna TEXT;
BEGIN
    SELECT
        TRUE,
        c.is_identity = 'YES',
        c.data_type
    INTO
        columna_existe,
        es_identity,
        tipo_columna
    FROM information_schema.columns AS c
    WHERE c.table_schema = 'energia'
      AND c.table_name = 'medidor'
      AND c.column_name = 'id_medidor';

    IF NOT FOUND OR NOT columna_existe THEN
        RAISE EXCEPTION
            'No existe la columna energia.medidor.id_medidor.';
    END IF;

    IF tipo_columna NOT IN (
        'smallint',
        'integer',
        'bigint'
    ) THEN
        RAISE EXCEPTION
            'energia.medidor.id_medidor debe ser entero. Tipo encontrado: %',
            tipo_columna;
    END IF;

    ALTER TABLE energia.medidor
        ALTER COLUMN id_medidor SET NOT NULL;

    IF NOT es_identity THEN
        ALTER TABLE energia.medidor
            ALTER COLUMN id_medidor DROP DEFAULT;

        ALTER TABLE energia.medidor
            ALTER COLUMN id_medidor
            ADD GENERATED BY DEFAULT AS IDENTITY;

        RAISE NOTICE
            'id_medidor fue convertido en columna IDENTITY.';
    ELSE
        RAISE NOTICE
            'id_medidor ya es una columna IDENTITY.';
    END IF;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 7. ASEGURAR CLAVE PRIMARIA DE id_medidor
-- =====================================================================

DO $$
DECLARE
    tiene_pk_id_medidor BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_constraint AS con
        JOIN pg_class AS rel
          ON rel.oid = con.conrelid
        JOIN pg_namespace AS nsp
          ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = 'energia'
          AND rel.relname = 'medidor'
          AND con.contype = 'p'
          AND pg_get_constraintdef(con.oid)
              ILIKE '%(id_medidor)%'
    )
    INTO tiene_pk_id_medidor;

    IF NOT tiene_pk_id_medidor THEN
        IF EXISTS (
            SELECT id_medidor
            FROM energia.medidor
            GROUP BY id_medidor
            HAVING COUNT(*) > 1
        ) THEN
            RAISE EXCEPTION
                'No puede crearse la PK de medidor: hay id_medidor duplicados.';
        END IF;

        ALTER TABLE energia.medidor
            ADD CONSTRAINT pk_medidor
            PRIMARY KEY (id_medidor);

        RAISE NOTICE
            'Clave primaria pk_medidor creada.';
    ELSE
        RAISE NOTICE
            'id_medidor ya pertenece a la clave primaria.';
    END IF;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 8. CORREGIR energia.medidor.calidad_enlace
-- =====================================================================
--
-- Problemas solucionados:
--
-- null value in column "calidad_enlace" violates not-null constraint
--
-- y:
--
-- violates check constraint "ck_medidor_enlace"
--
-- Se utiliza NUMERIC(5,4), que permite:
--
-- 0.0000
-- 0.9500
-- 0.9700
-- 1.0000
-- =====================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'energia'
          AND table_name = 'medidor'
          AND column_name = 'calidad_enlace'
    ) THEN
        ALTER TABLE energia.medidor
            ADD COLUMN calidad_enlace NUMERIC(5,4);

        RAISE NOTICE
            'Columna calidad_enlace creada.';
    END IF;
END
$$ LANGUAGE plpgsql;


-- Eliminar temporalmente la restriccion anterior.

ALTER TABLE energia.medidor
    DROP CONSTRAINT IF EXISTS ck_medidor_enlace;


-- Eliminar temporalmente el DEFAULT anterior.

ALTER TABLE energia.medidor
    ALTER COLUMN calidad_enlace DROP DEFAULT;


-- Convertir valores fuera de rango antes de cambiar el tipo.
--
-- Valores NULL se convierten a 0.9500.
-- Valores menores que 0 se convierten a 0.
-- Valores mayores que 1 se convierten a 1.

UPDATE energia.medidor
SET calidad_enlace =
    CASE
        WHEN calidad_enlace IS NULL THEN 0.9500
        WHEN calidad_enlace::NUMERIC < 0 THEN 0.0000
        WHEN calidad_enlace::NUMERIC > 1 THEN 1.0000
        ELSE calidad_enlace::NUMERIC
    END;


-- Corregir el tipo.

ALTER TABLE energia.medidor
    ALTER COLUMN calidad_enlace
    TYPE NUMERIC(5,4)
    USING calidad_enlace::NUMERIC(5,4);


-- Configurar valor predeterminado.

ALTER TABLE energia.medidor
    ALTER COLUMN calidad_enlace
    SET DEFAULT 0.9500;


-- Mantener la columna obligatoria.

ALTER TABLE energia.medidor
    ALTER COLUMN calidad_enlace
    SET NOT NULL;


-- Recrear la restriccion de rango.

ALTER TABLE energia.medidor
    ADD CONSTRAINT ck_medidor_enlace
    CHECK (
        calidad_enlace >= 0.0000
        AND calidad_enlace <= 1.0000
    );


-- =====================================================================
-- 9. SINCRONIZAR IDENTITY DE id_medidor
-- =====================================================================
--
-- Si la tabla contiene medidores restaurados, el siguiente identificador
-- debe ser mayor que el MAX(id_medidor).
-- =====================================================================

DO $$
DECLARE
    nombre_secuencia TEXT;
    siguiente_valor BIGINT;
BEGIN
    SELECT pg_get_serial_sequence(
        'energia.medidor',
        'id_medidor'
    )
    INTO nombre_secuencia;

    SELECT COALESCE(MAX(id_medidor), 0) + 1
    INTO siguiente_valor
    FROM energia.medidor;

    IF nombre_secuencia IS NOT NULL THEN
        PERFORM setval(
            nombre_secuencia::regclass,
            siguiente_valor,
            FALSE
        );

        RAISE NOTICE
            'Secuencia de id_medidor sincronizada. Siguiente valor: %',
            siguiente_valor;
    ELSE
        RAISE WARNING
            'No fue posible obtener la secuencia asociada a id_medidor.';
    END IF;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 10. CONFIRMAR CORRECCIONES ESTRUCTURALES
-- =====================================================================

COMMIT;


-- =====================================================================
-- 11. PERMISOS DE BASE DE DATOS
-- =====================================================================

GRANT CONNECT
ON DATABASE energia_hsd
TO equipo_hsd;


-- =====================================================================
-- 12. PERMISOS DEL ESQUEMA
-- =====================================================================

GRANT USAGE
ON SCHEMA energia
TO equipo_hsd;


-- No es necesario otorgar CREATE para ejecutar los generadores.
-- Si equipo_hsd tambien debe crear tablas, descomenta:
--
-- GRANT CREATE
-- ON SCHEMA energia
-- TO equipo_hsd;


-- =====================================================================
-- 13. PERMISOS SOBRE TABLAS EXISTENTES
-- =====================================================================

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
ON ALL TABLES IN SCHEMA energia
TO equipo_hsd;


-- =====================================================================
-- 14. PERMISOS SOBRE SECUENCIAS EXISTENTES
-- =====================================================================

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA energia
TO equipo_hsd;


-- =====================================================================
-- 15. PERMISOS SOBRE FUNCIONES EXISTENTES
-- =====================================================================

GRANT EXECUTE
ON ALL FUNCTIONS IN SCHEMA energia
TO equipo_hsd;


-- =====================================================================
-- 16. PERMISOS PREDETERMINADOS PARA OBJETOS FUTUROS
-- =====================================================================
--
-- IMPORTANTE:
-- ALTER DEFAULT PRIVILEGES se aplica a los objetos futuros creados
-- por el usuario que ejecuta estas instrucciones.
--
-- Lo ideal es ejecutar este script como el mismo propietario con el
-- que se crean las tablas del proyecto.
-- =====================================================================

ALTER DEFAULT PRIVILEGES IN SCHEMA energia
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
ON TABLES
TO equipo_hsd;

ALTER DEFAULT PRIVILEGES IN SCHEMA energia
GRANT USAGE, SELECT, UPDATE
ON SEQUENCES
TO equipo_hsd;

ALTER DEFAULT PRIVILEGES IN SCHEMA energia
GRANT EXECUTE
ON FUNCTIONS
TO equipo_hsd;


-- =====================================================================
-- 17. VALIDAR PERMISOS
-- =====================================================================

SELECT
    has_database_privilege(
        'equipo_hsd',
        'energia_hsd',
        'CONNECT'
    ) AS puede_conectarse,

    has_schema_privilege(
        'equipo_hsd',
        'energia',
        'USAGE'
    ) AS puede_usar_esquema,

    has_table_privilege(
        'equipo_hsd',
        'energia.calendario',
        'SELECT'
    ) AS puede_consultar_calendario,

    has_table_privilege(
        'equipo_hsd',
        'energia.calendario',
        'INSERT'
    ) AS puede_insertar_calendario,

    has_table_privilege(
        'equipo_hsd',
        'energia.servicio',
        'INSERT'
    ) AS puede_insertar_servicios,

    has_table_privilege(
        'equipo_hsd',
        'energia.medidor',
        'INSERT'
    ) AS puede_insertar_medidores,

    has_table_privilege(
        'equipo_hsd',
        'energia.lectura',
        'INSERT'
    ) AS puede_insertar_lecturas;


-- =====================================================================
-- 18. VALIDAR ESTRUCTURA DE id_medidor
-- =====================================================================

SELECT
    column_name,
    data_type,
    is_nullable,
    column_default,
    is_identity,
    identity_generation
FROM information_schema.columns
WHERE table_schema = 'energia'
  AND table_name = 'medidor'
  AND column_name = 'id_medidor';


-- Resultado esperado:
--
-- column_name         id_medidor
-- is_nullable         NO
-- is_identity         YES
-- identity_generation BY DEFAULT


-- =====================================================================
-- 19. VALIDAR ESTRUCTURA DE calidad_enlace
-- =====================================================================

SELECT
    column_name,
    data_type,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'energia'
  AND table_name = 'medidor'
  AND column_name = 'calidad_enlace';


-- Resultado esperado:
--
-- column_name       calidad_enlace
-- data_type         numeric
-- numeric_precision 5
-- numeric_scale     4
-- is_nullable       NO
-- column_default    0.9500


-- =====================================================================
-- 20. VALIDAR RESTRICCION ck_medidor_enlace
-- =====================================================================

SELECT
    con.conname AS restriccion,
    pg_get_constraintdef(con.oid) AS definicion
FROM pg_constraint AS con
JOIN pg_class AS rel
  ON rel.oid = con.conrelid
JOIN pg_namespace AS nsp
  ON nsp.oid = rel.relnamespace
WHERE nsp.nspname = 'energia'
  AND rel.relname = 'medidor'
  AND con.conname = 'ck_medidor_enlace';


-- =====================================================================
-- 21. VALIDAR CALIDAD DE ENLACE
-- =====================================================================

SELECT
    COUNT(*) AS total_medidores,
    MIN(calidad_enlace) AS calidad_minima,
    ROUND(AVG(calidad_enlace), 4) AS calidad_promedio,
    MAX(calidad_enlace) AS calidad_maxima,
    COUNT(*) FILTER (
        WHERE calidad_enlace IS NULL
    ) AS calidades_nulas,
    COUNT(*) FILTER (
        WHERE calidad_enlace < 0
           OR calidad_enlace > 1
    ) AS calidades_fuera_de_rango
FROM energia.medidor;


-- calidades_nulas debe ser 0.
-- calidades_fuera_de_rango debe ser 0.


-- =====================================================================
-- 22. CONTAR REGISTROS PRINCIPALES
-- =====================================================================

SELECT
    'alerta' AS tabla,
    COUNT(*) AS registros
FROM energia.alerta

UNION ALL

SELECT
    'calendario',
    COUNT(*)
FROM energia.calendario

UNION ALL

SELECT
    'evento',
    COUNT(*)
FROM energia.evento

UNION ALL

SELECT
    'lectura',
    COUNT(*)
FROM energia.lectura

UNION ALL

SELECT
    'medidor',
    COUNT(*)
FROM energia.medidor

UNION ALL

SELECT
    'perfil_carga_horaria',
    COUNT(*)
FROM energia.perfil_carga_horaria

UNION ALL

SELECT
    'periodo_facturacion',
    COUNT(*)
FROM energia.periodo_facturacion

UNION ALL

SELECT
    'servicio',
    COUNT(*)
FROM energia.servicio

UNION ALL

SELECT
    'tarifa',
    COUNT(*)
FROM energia.tarifa

UNION ALL

SELECT
    'tipo_evento',
    COUNT(*)
FROM energia.tipo_evento

UNION ALL

SELECT
    'tipo_servicio',
    COUNT(*)
FROM energia.tipo_servicio

UNION ALL

SELECT
    'zona',
    COUNT(*)
FROM energia.zona

ORDER BY tabla;


-- =====================================================================
-- 23. VALIDAR INTEGRIDAD REFERENCIAL
-- =====================================================================
--
-- Todas las validaciones deben devolver 0 inconsistencias.
-- =====================================================================

SELECT
    'medidores_sin_servicio' AS validacion,
    COUNT(*) AS inconsistencias
FROM energia.medidor AS m
LEFT JOIN energia.servicio AS s
  ON s.id_servicio = m.id_servicio
WHERE s.id_servicio IS NULL

UNION ALL

SELECT
    'servicios_sin_zona',
    COUNT(*)
FROM energia.servicio AS s
LEFT JOIN energia.zona AS z
  ON z.id_zona = s.id_zona
WHERE z.id_zona IS NULL

UNION ALL

SELECT
    'servicios_sin_tipo',
    COUNT(*)
FROM energia.servicio AS s
LEFT JOIN energia.tipo_servicio AS ts
  ON ts.id_tipo_servicio = s.id_tipo_servicio
WHERE ts.id_tipo_servicio IS NULL

UNION ALL

SELECT
    'eventos_sin_medidor',
    COUNT(*)
FROM energia.evento AS e
LEFT JOIN energia.medidor AS m
  ON m.id_medidor = e.id_medidor
WHERE m.id_medidor IS NULL

UNION ALL

SELECT
    'lecturas_sin_medidor',
    COUNT(*)
FROM energia.lectura AS l
LEFT JOIN energia.medidor AS m
  ON m.id_medidor = l.id_medidor
WHERE m.id_medidor IS NULL

UNION ALL

SELECT
    'eventos_con_fechas_invalidas',
    COUNT(*)
FROM energia.evento
WHERE ts_fin <= ts_inicio

UNION ALL

SELECT
    'lecturas_reales_negativas',
    COUNT(*)
FROM energia.lectura
WHERE consumo_real_kwh < 0

UNION ALL

SELECT
    'lecturas_reales_nulas',
    COUNT(*)
FROM energia.lectura
WHERE consumo_real_kwh IS NULL

UNION ALL

SELECT
    'medidores_con_enlace_invalido',
    COUNT(*)
FROM energia.medidor
WHERE calidad_enlace IS NULL
   OR calidad_enlace < 0
   OR calidad_enlace > 1

ORDER BY validacion;


-- =====================================================================
-- 24. VALIDAR DUPLICADOS
-- =====================================================================

SELECT
    id_medidor,
    ts,
    COUNT(*) AS repeticiones
FROM energia.lectura
GROUP BY
    id_medidor,
    ts
HAVING COUNT(*) > 1
ORDER BY repeticiones DESC
LIMIT 100;


-- Debe devolver 0 filas.


-- =====================================================================
-- 25. VALIDAR PERFILES HORARIOS
-- =====================================================================

SELECT
    id_tipo_servicio,
    tipo_dia,
    ROUND(SUM(factor), 4) AS suma_factores
FROM energia.perfil_carga_horaria
GROUP BY
    id_tipo_servicio,
    tipo_dia
HAVING ABS(SUM(factor) - 24.0) > 0.01
ORDER BY
    id_tipo_servicio,
    tipo_dia;


-- Debe devolver 0 filas.


-- =====================================================================
-- 26. VALIDAR COLUMNAS OBLIGATORIAS SIN DEFAULT
-- =====================================================================
--
-- Esta consulta es informativa.
--
-- Las columnas mostradas deben recibir un valor desde Python,
-- pertenecer a una clave foranea o configurarse con DEFAULT.
-- =====================================================================

SELECT
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default,
    is_identity
FROM information_schema.columns
WHERE table_schema = 'energia'
  AND is_nullable = 'NO'
  AND column_default IS NULL
  AND is_identity = 'NO'
ORDER BY
    table_name,
    ordinal_position;


-- =====================================================================
-- 27. LISTAR SECUENCIAS
-- =====================================================================

SELECT
    sequence_schema,
    sequence_name,
    data_type,
    start_value,
    minimum_value,
    maximum_value,
    increment
FROM information_schema.sequences
WHERE sequence_schema = 'energia'
ORDER BY sequence_name;


-- =====================================================================
-- 28. RESUMEN FINAL
-- =====================================================================

SELECT
    current_database() AS base_datos,
    current_user AS ejecutado_por,
    'equipo_hsd' AS usuario_aplicacion,
    (
        SELECT COUNT(*)
        FROM energia.calendario
    ) AS calendario,
    (
        SELECT COUNT(*)
        FROM energia.perfil_carga_horaria
    ) AS perfiles,
    (
        SELECT COUNT(*)
        FROM energia.servicio
    ) AS servicios,
    (
        SELECT COUNT(*)
        FROM energia.medidor
    ) AS medidores,
    (
        SELECT COUNT(*)
        FROM energia.evento
    ) AS eventos,
    (
        SELECT COUNT(*)
        FROM energia.lectura
    ) AS lecturas,
    (
        SELECT COUNT(*)
        FROM energia.alerta
    ) AS alertas,
    (
        SELECT COUNT(*)
        FROM energia.periodo_facturacion
    ) AS periodos_facturacion;


-- =====================================================================
-- 29. LIMPIEZA OPCIONAL DE DATOS SINTETICOS
-- =====================================================================
--
-- ADVERTENCIA:
-- Este bloque esta comentado porque ELIMINA DATOS.
--
-- Descomentalo solamente si quieres ejecutar nuevamente main.py
-- desde cero.
--
-- Conserva:
--
-- - zona;
-- - tarifa;
-- - tipo_servicio;
-- - tipo_evento;
-- - perfil_carga_horaria;
-- - calendario.
--
-- Elimina:
--
-- - alerta;
-- - lectura;
-- - periodo_facturacion;
-- - evento;
-- - medidor;
-- - servicio.
-- =====================================================================

/*

BEGIN;

TRUNCATE TABLE
    energia.alerta,
    energia.lectura,
    energia.periodo_facturacion,
    energia.evento,
    energia.medidor,
    energia.servicio
RESTART IDENTITY;

COMMIT;

*/


-- =====================================================================
-- 30. LIMPIEZA EXTREMA OPCIONAL
-- =====================================================================
--
-- Usar solamente si el bloque anterior falla por una clave foranea
-- no incluida.
--
-- CASCADE puede limpiar automaticamente otras tablas dependientes.
--
-- ADVERTENCIA: ELIMINA DATOS.
-- =====================================================================

/*

BEGIN;

TRUNCATE TABLE energia.servicio
RESTART IDENTITY
CASCADE;

COMMIT;

*/


-- =====================================================================
-- FIN DEL SCRIPT
-- =====================================================================

SELECT
    'CORRECCIONES Y VALIDACIONES FINALIZADAS' AS resultado,
    CURRENT_TIMESTAMP AS fecha_ejecucion;