-- =====================================================================
-- configurar_permisos.sql
-- HyperDataSynthetic
--
-- Base de datos: energia_hsd
-- Esquema: energia
-- Usuario de la aplicacion: equipo_hsd
--
-- Ejecutar DESPUES de restaurar energia_hsd.backup.
-- Ejecutar conectado a energia_hsd con un usuario administrador
-- (por ejemplo, postgres).
-- =====================================================================


-- =====================================================================
-- 1. VERIFICAR QUE ESTAMOS EN LA BASE CORRECTA
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
-- 2. COMPROBAR QUE EXISTE EL ESQUEMA
-- =====================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.schemata
        WHERE schema_name = 'energia'
    ) THEN
        RAISE EXCEPTION
            'No existe el esquema energia. Restaura primero el backup.';
    END IF;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 3. COMPROBAR QUE EXISTE EL USUARIO equipo_hsd
-- =====================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'equipo_hsd'
    ) THEN
        RAISE EXCEPTION
            'No existe el usuario equipo_hsd. Debes crearlo antes de ejecutar este script.';
    END IF;
END
$$ LANGUAGE plpgsql;


-- =====================================================================
-- 4. PERMISO PARA CONECTARSE A LA BASE
-- =====================================================================

GRANT CONNECT
ON DATABASE energia_hsd
TO equipo_hsd;


-- =====================================================================
-- 5. PERMISO PARA USAR EL ESQUEMA energia
-- =====================================================================

GRANT USAGE
ON SCHEMA energia
TO equipo_hsd;


-- =====================================================================
-- 6. PERMISOS SOBRE TODAS LAS TABLAS EXISTENTES
-- =====================================================================

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE
ON ALL TABLES IN SCHEMA energia
TO equipo_hsd;


-- =====================================================================
-- 7. PERMISOS SOBRE TODAS LAS SECUENCIAS EXISTENTES
-- =====================================================================

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA energia
TO equipo_hsd;


-- =====================================================================
-- 8. PERMISOS SOBRE TODAS LAS FUNCIONES EXISTENTES
-- =====================================================================

GRANT EXECUTE
ON ALL FUNCTIONS IN SCHEMA energia
TO equipo_hsd;


-- =====================================================================
-- 9. PERMISOS PARA OBJETOS FUTUROS
-- =====================================================================
--
-- IMPORTANTE:
-- Estos permisos se aplican a objetos creados posteriormente por el
-- usuario que ejecuta ALTER DEFAULT PRIVILEGES.
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
-- 10. VALIDAR PERMISOS PRINCIPALES
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
        'energia.medidor',
        'SELECT'
    ) AS puede_consultar,

    has_table_privilege(
        'equipo_hsd',
        'energia.medidor',
        'INSERT'
    ) AS puede_insertar,

    has_table_privilege(
        'equipo_hsd',
        'energia.medidor',
        'UPDATE'
    ) AS puede_actualizar,

    has_table_privilege(
        'equipo_hsd',
        'energia.medidor',
        'DELETE'
    ) AS puede_eliminar;


-- =====================================================================
-- FIN
-- =====================================================================

SELECT
    'PERMISOS CONFIGURADOS CORRECTAMENTE' AS resultado;