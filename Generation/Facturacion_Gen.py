"""Generador de periodos mensuales de facturacion para HyperDataSynthetic.

Responsabilidad:
- Resume las lecturas horarias por servicio y mes.
- Genera un recibo mensual por servicio.
- Calcula consumo real y consumo registrado por el contador.
- Conserva continuidad entre la lectura inicial y final de cada periodo.
- Clasifica servicios domesticos de alto consumo sin cambiar la estructura BD.
- Inserta filas en energia.periodo_facturacion.

Orden recomendado:
    Lecturas_Gen.py -> Facturacion_Gen.py
"""

from __future__ import annotations

import calendar
import random
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterator


# ======================================================================
# CONFIGURACION
# ======================================================================


def _seccion_generacion(config: dict[str, Any]) -> dict[str, Any]:
    generation = config.get("generation")
    return generation if isinstance(generation, dict) else config


def _config_facturacion(config: dict[str, Any]) -> dict[str, Any]:
    generation = _seccion_generacion(config)
    section = generation.get("billing", generation.get("facturacion", {}))
    return section if isinstance(section, dict) else {}


def _obtener(config: dict[str, Any], *nombres: str) -> Any:
    for nombre in nombres:
        if nombre in config:
            return config[nombre]
    raise KeyError(f"Falta uno de estos parametros: {', '.join(nombres)}")


def _convertir_fecha(valor: Any, nombre: str) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError as error:
            raise ValueError(
                f"{nombre} debe usar el formato YYYY-MM-DD: {valor!r}"
            ) from error
    raise TypeError(f"{nombre} debe ser una fecha o texto YYYY-MM-DD")


def _meses_entre(desde: date, hasta: date) -> Iterator[tuple[date, date]]:
    """Devuelve periodos mensuales inclusivos recortados al rango."""
    actual = date(desde.year, desde.month, 1)

    while actual <= hasta:
        ultimo_dia = calendar.monthrange(actual.year, actual.month)[1]
        fin_mes = date(actual.year, actual.month, ultimo_dia)

        inicio_periodo = max(desde, actual)
        fin_periodo = min(hasta, fin_mes)
        yield inicio_periodo, fin_periodo

        if actual.month == 12:
            actual = date(actual.year + 1, 1, 1)
        else:
            actual = date(actual.year, actual.month + 1, 1)


def _dinero_kwh(valor: Any) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ======================================================================
# CONSULTAS
# ======================================================================


def _cargar_servicios(connection: Any) -> list[dict[str, Any]]:
    sql = """
        SELECT
            s.id_servicio,
            s.id_tarifa,
            t.codigo,
            t.categoria,
            t.limite_dac_kwh_mes
        FROM energia.servicio s
        JOIN energia.tarifa t
          ON t.id_tarifa = s.id_tarifa
        ORDER BY s.id_servicio
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    if not filas:
        raise RuntimeError("energia.servicio esta vacia.")

    return [
        {
            "id_servicio": int(fila[0]),
            "id_tarifa": int(fila[1]),
            "codigo_tarifa": fila[2],
            "categoria_tarifa": fila[3],
            "limite_dac": int(fila[4]) if fila[4] is not None else None,
        }
        for fila in filas
    ]


def _buscar_tarifa_dac(connection: Any) -> int | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id_tarifa
            FROM energia.tarifa
            WHERE UPPER(codigo) = 'DAC'
            ORDER BY id_tarifa
            LIMIT 1
            """
        )
        fila = cursor.fetchone()
    return int(fila[0]) if fila else None


def _contar_periodos(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM energia.periodo_facturacion")
        return int(cursor.fetchone()[0])


def _siguiente_id(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(MAX(id_periodo), 0) + 1 "
            "FROM energia.periodo_facturacion"
        )
        return int(cursor.fetchone()[0])


def _resumen_periodo(
    connection: Any,
    inicio: date,
    fin: date,
) -> dict[int, tuple[Decimal, Decimal]]:
    """Devuelve consumo de contador y real por servicio.

    Para eventos que NO afectan el contador, como perdida de comunicacion,
    el contador conserva el consumo real aunque consumo_kwh sea NULL.
    Para eventos que SI afectan el contador, se utiliza consumo_kwh; si
    estuviera NULL se considera cero.
    """
    inicio_ts = datetime.combine(inicio, datetime.min.time())
    fin_exclusivo = datetime.combine(fin + timedelta(days=1), datetime.min.time())

    sql = """
        SELECT
            s.id_servicio,
            COALESCE(
                SUM(
                    CASE
                        WHEN l.id_evento IS NOT NULL
                         AND te.afecta_acumulado = FALSE
                            THEN l.consumo_real_kwh
                        ELSE COALESCE(l.consumo_kwh, 0)
                    END
                ),
                0
            ) AS consumo_contador,
            COALESCE(SUM(l.consumo_real_kwh), 0) AS consumo_real
        FROM energia.servicio s
        LEFT JOIN energia.medidor m
          ON m.id_servicio = s.id_servicio
        LEFT JOIN energia.lectura l
          ON l.id_medidor = m.id_medidor
         AND l.ts >= %s
         AND l.ts < %s
        LEFT JOIN energia.evento e
          ON e.id_evento = l.id_evento
        LEFT JOIN energia.tipo_evento te
          ON te.id_tipo_evento = e.id_tipo_evento
        GROUP BY s.id_servicio
        ORDER BY s.id_servicio
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (inicio_ts, fin_exclusivo))
        filas = cursor.fetchall()

    return {
        int(fila[0]): (_dinero_kwh(fila[1]), _dinero_kwh(fila[2]))
        for fila in filas
    }


# ======================================================================
# CONSTRUCCION
# ======================================================================


def construir_facturacion(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> tuple[list[tuple[Any, ...]], dict[int, int]]:
    """Construye recibos y devuelve cambios finales de tarifa."""
    del rules

    generation = _seccion_generacion(config)
    billing = _config_facturacion(config)

    fecha_inicio = _convertir_fecha(
        _obtener(generation, "start_date", "fecha_inicial", "fecha_desde"),
        "fecha inicial",
    )
    fecha_fin = _convertir_fecha(
        _obtener(generation, "end_date", "fecha_final", "fecha_hasta"),
        "fecha final",
    )

    if fecha_fin < fecha_inicio:
        raise ValueError("La fecha final no puede ser anterior a la fecha inicial")

    semilla_base = int(generation.get("seed", generation.get("semilla", 42)))
    semilla = int(billing.get("seed", semilla_base + 6000))
    rng = random.Random(semilla)

    contador_min = float(billing.get("initial_meter_reading_min_kwh", 0.0))
    contador_max = float(billing.get("initial_meter_reading_max_kwh", 10000.0))
    if contador_min < 0 or contador_max < contador_min:
        raise ValueError("Rango de lectura inicial invalido")

    aplicar_dac_siguiente_mes = bool(
        billing.get("apply_dac_next_month", True)
    )

    servicios = _cargar_servicios(connection)
    tarifa_dac = _buscar_tarifa_dac(connection)
    id_periodo = _siguiente_id(connection)

    estado = {}
    for servicio in servicios:
        estado[servicio["id_servicio"]] = {
            "contador": _dinero_kwh(rng.uniform(contador_min, contador_max)),
            "tarifa_actual": servicio["id_tarifa"],
            "categoria": servicio["categoria_tarifa"],
            "limite_dac": servicio["limite_dac"],
            "es_dac": servicio["codigo_tarifa"].upper() == "DAC",
        }

    filas = []

    for inicio_periodo, fin_periodo in _meses_entre(fecha_inicio, fecha_fin):
        resumen = _resumen_periodo(connection, inicio_periodo, fin_periodo)

        for servicio in servicios:
            id_servicio = servicio["id_servicio"]
            consumo_contador, consumo_real = resumen[id_servicio]
            servicio_estado = estado[id_servicio]

            registro_inicial = servicio_estado["contador"]
            registro_final = _dinero_kwh(registro_inicial + consumo_contador)
            tarifa_aplicada = servicio_estado["tarifa_actual"]

            limite = servicio_estado["limite_dac"]
            clasificacion_dac = bool(
                servicio_estado["es_dac"]
                or (
                    servicio_estado["categoria"] == "DOMESTICA"
                    and limite is not None
                    and consumo_real > Decimal(limite)
                )
            )

            folio = (
                f"RB-{inicio_periodo.year:04d}-"
                f"{inicio_periodo.month:02d}-{id_servicio:06d}"
            )

            filas.append(
                (
                    id_periodo,
                    id_servicio,
                    folio,
                    inicio_periodo,
                    fin_periodo,
                    tarifa_aplicada,
                    registro_inicial,
                    registro_final,
                    consumo_real,
                    clasificacion_dac,
                )
            )

            servicio_estado["contador"] = registro_final

            # El recibo actual conserva su tarifa. La reclasificacion entra
            # en vigor para el siguiente mes, si asi se configura.
            if (
                aplicar_dac_siguiente_mes
                and clasificacion_dac
                and tarifa_dac is not None
            ):
                servicio_estado["tarifa_actual"] = tarifa_dac
                servicio_estado["es_dac"] = True

            id_periodo += 1

    cambios_tarifa = {
        id_servicio: datos["tarifa_actual"]
        for id_servicio, datos in estado.items()
        if datos["tarifa_actual"]
        != next(
            srv["id_tarifa"]
            for srv in servicios
            if srv["id_servicio"] == id_servicio
        )
    }

    return filas, cambios_tarifa


# ======================================================================
# INSERCION
# ======================================================================


def generar_facturacion(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    """Genera e inserta los periodos de facturacion."""
    billing = _config_facturacion(config)
    replace_existing = bool(billing.get("replace_existing", False))
    update_service_tariff = bool(billing.get("update_service_tariff", False))
    batch_size = int(billing.get("batch_size", 5000))

    if batch_size <= 0:
        raise ValueError("billing.batch_size debe ser mayor que cero")

    existentes = _contar_periodos(connection)
    if existentes and not replace_existing:
        raise RuntimeError(
            f"energia.periodo_facturacion ya contiene {existentes:,} filas. "
            "Para evitar duplicados, conserva la tabla vacia o configura "
            "billing.replace_existing: true."
        )

    sql = """
        INSERT INTO energia.periodo_facturacion (
            id_periodo,
            id_servicio,
            folio,
            fecha_inicio,
            fecha_fin,
            id_tarifa_aplicada,
            registro_inicial_kwh,
            registro_final_kwh,
            consumo_real_kwh,
            clasificacion_dac
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    try:
        if replace_existing and existentes:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM energia.periodo_facturacion")

        filas, cambios_tarifa = construir_facturacion(connection, config, rules)

        with connection.cursor() as cursor:
            for inicio in range(0, len(filas), batch_size):
                cursor.executemany(sql, filas[inicio:inicio + batch_size])

            if update_service_tariff and cambios_tarifa:
                cursor.executemany(
                    """
                    UPDATE energia.servicio
                    SET id_tarifa = %s
                    WHERE id_servicio = %s
                    """,
                    [
                        (id_tarifa, id_servicio)
                        for id_servicio, id_tarifa in cambios_tarifa.items()
                    ],
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    periodos_dac = sum(1 for fila in filas if fila[9])
    servicios_facturados = len({fila[1] for fila in filas})

    print(f"[OK] Periodos generados: {len(filas):,}")
    print(f"[OK] Servicios facturados: {servicios_facturados:,}")
    print(f"[OK] Periodos con clasificacion DAC: {periodos_dac:,}")
    print(f"[OK] Servicios reclasificados: {len(cambios_tarifa):,}")

    if cambios_tarifa and not update_service_tariff:
        print(
            "[INFO] Las nuevas tarifas se reflejan en periodos posteriores, "
            "pero energia.servicio no se modifica porque "
            "billing.update_service_tariff es false."
        )

    return len(filas)


# Alias uniforme para main.py.
def generar(connection: Any, config: dict[str, Any], rules: dict[str, Any]) -> int:
    return generar_facturacion(connection, config, rules)
