from database.connection import get_connection


LECTURA_COLUMNS = (
    "id_medidor",
    "ts",
    "consumo_kwh",
    "consumo_real_kwh",
    "id_evento",
)


def copy_lecturas(rows):
    """
    Inserta un iterable de lecturas utilizando
    PostgreSQL COPY.

    Cada elemento debe contener:

    (
        id_medidor,
        ts,
        consumo_kwh,
        consumo_real_kwh,
        id_evento
    )
    """

    sql = """
        COPY energia.lectura (
            id_medidor,
            ts,
            consumo_kwh,
            consumo_real_kwh,
            id_evento
        )
        FROM STDIN
    """

    count = 0

    with get_connection() as conn:

        with conn.cursor() as cur:

            with cur.copy(sql) as copy:

                for row in rows:

                    copy.write_row(row)

                    count += 1

        conn.commit()

    return count