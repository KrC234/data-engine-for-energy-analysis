import psycopg

from config.settings import settings


def get_connection():
    """
    Crea una nueva conexion PostgreSQL.
    """

    settings.validate()

    return psycopg.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        connect_timeout=settings.DB_CONNECT_TIMEOUT,
    )


def test_connection():
    """
    Comprueba conexion, base de datos y servidor.
    """

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    version();
                """
            )

            database, user, version = cur.fetchone()

            return {
                "database": database,
                "user": user,
                "version": version,
            }