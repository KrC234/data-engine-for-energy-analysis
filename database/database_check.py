"""
    Verificacion de la base de datos (database/database_check.py)

    Comprueba que el esquema contenga todas las tablas requeridas
    por HyperDataSynthetic antes de iniciar una corrida.
"""


EXPECTED_TABLES = {
    "corrida_generacion",
    "zona",
    "tarifa",
    "tipo_servicio",
    "tipo_evento",
    "perfil_carga_horaria",
    "calendario",
    "servicio",
    "medidor",
    "evento",
    "lectura",
    "alerta",
    "periodo_facturacion",
}


def get_tables(connection, schema):
    """
    Obtiene las tablas del esquema configurado.
    Incluye tablas normales y particionadas.
    """
    query = """
        SELECT c.relname
        FROM pg_catalog.pg_class c
        INNER JOIN pg_catalog.pg_namespace n
            ON n.oid = c.relnamespace
        WHERE n.nspname = %s
          AND c.relkind IN ('r', 'p')
        ORDER BY c.relname;
    """
    with connection.cursor() as cur:
        cur.execute(query, (schema,))
        return {row[0] for row in cur.fetchall()}


def check_database(connection, schema="energia"):
    """
    Verifica que existan todas las tablas requeridas.
    """
    existing = get_tables(connection, schema)

    missing = EXPECTED_TABLES - existing
    found = EXPECTED_TABLES & existing

    return {
        "existing": existing,
        "found": found,
        "missing": missing,
        "valid": len(missing) == 0,
        "required": len(EXPECTED_TABLES),
        "found_count": len(found),
    }