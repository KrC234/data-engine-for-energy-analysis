"""
    MECANISMO DE INSERCION POR LOTES (database/insertar.py)

    LOTE = batch_size registros que Python mantiene temporalmente en memoria
           (por defecto 100,000, definido en config/generation.yaml).
    COPY = mecanismo usado para mandar ese lote a PostgreSQL:
           COPY energia.<tabla> (col1, col2, ...) FROM STDIN

    El flujo es:
      1. El generador produce hasta batch_size registros.
      2. COPY envia el lote completo a PostgreSQL (un solo comando).
      3. Se vacia la lista en Python.
      4. Se genera el siguiente lote.

    Asi se evita mantener las ~10.8 millones de lecturas en RAM.

    El formato utilizado es el texto nativo de PostgreSQL (separador
    TAB, NULL como backslash-N), que psycopg maneja de forma
    determinista al pasar una secuencia de valores por registro.
"""

from datetime import date, datetime


def normalizar_valor(valor):
    """
    Convierte un valor Python a una representacion que PostgreSQL
    acepte dentro de un COPY en formato texto.

    - None        -> None (psycopg lo escribe como backslash-N = NULL)
    - bool        -> 1 / 0
    - date/datetime -> ISO 8601
    - float/int   -> numerico
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return 1 if valor else 0
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def copy_lote(connection, tabla, columnas, filas, etiqueta="", acumulado=0):
    """
    Envia un lote concreto a PostgreSQL mediante COPY ... FROM STDIN
    en formato texto nativo (TAB, backslash-N para NULL).

    tabla    : nombre de la tabla dentro del esquema (p.ej. "servicio").
    columnas : lista con los nombres de columnas en orden.
    filas    : lista de listas/tuplas, una por registro.
    """
    columnas_sql = ", ".join(columnas)
    comando = f"COPY energia.{tabla} ({columnas_sql}) FROM STDIN"

    with connection.cursor() as cur:
        with cur.copy(comando) as copia:
            for fila in filas:
                copia.write_row([normalizar_valor(valor) for valor in fila])

    if etiqueta:
        total = acumulado + len(filas)
        print(
            f"    {etiqueta}: lote de {len(filas)} "
            f"registros -> energia.{tabla} (acumulado: {total})"
        )

    return len(filas)


def insertar_por_lotes(connection, tabla, columnas, filas, batch_size, etiqueta=""):
    """
    Recorre el iterable `filas` agrupandolo en lotes de `batch_size`
    registros y envia cada lote con COPY.

    Devuelve el total de registros insertados.
    """
    total = 0
    lote = []

    for fila in filas:
        lote.append(fila)
        if len(lote) >= batch_size:
            total += copy_lote(
                connection, tabla, columnas, lote,
                etiqueta=etiqueta, acumulado=total,
            )
            lote = []

    if lote:
        total += copy_lote(
            connection, tabla, columnas, lote,
            etiqueta=etiqueta, acumulado=total,
        )

    return total