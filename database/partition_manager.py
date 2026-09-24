from datetime import date

from psycopg import sql

from database.connection import get_connection
from config.settings import settings


def next_month(current: date) -> date:

    if current.month == 12:
        return date(
            current.year + 1,
            1,
            1
        )

    return date(
        current.year,
        current.month + 1,
        1
    )


def ensure_partition(year: int, month: int):

    start = date(year, month, 1)
    end = next_month(start)

    table_name = (
        f"lectura_{year}_{month:02d}"
    )

    query = sql.SQL(
        """
        CREATE TABLE IF NOT EXISTS {}.{}
        PARTITION OF {}.lectura
        FOR VALUES FROM (%s) TO (%s);
        """
    ).format(
        sql.Identifier(settings.DB_SCHEMA),
        sql.Identifier(table_name),
        sql.Identifier(settings.DB_SCHEMA),
    )

    with get_connection() as conn:

        with conn.cursor() as cur:

            cur.execute(
                query,
                (start, end)
            )

        conn.commit()

    return table_name