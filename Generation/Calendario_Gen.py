"""Generador del calendario sintético de HyperDataSynthetic.

Genera una fila por fecha en energia.calendario usando:
- config/generation.yaml: periodo y semilla.
- config/rules.yaml: temperaturas, factores estacionales, festivos y vacaciones.

No modifica la estructura de PostgreSQL. Solo inserta o actualiza filas en
energia.calendario.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any, Iterable


MESES = {
    1: "january",
    2: "february",
    3: "march",
    4: "april",
    5: "may",
    6: "june",
    7: "july",
    8: "august",
    9: "september",
    10: "october",
    11: "november",
    12: "december",
}


def _seccion_generacion(config: dict[str, Any]) -> dict[str, Any]:
    """Acepta parámetros en la raíz o dentro de la clave generation."""
    generation = config.get("generation")
    return generation if isinstance(generation, dict) else config


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


def _rango_fechas(inicio: date, fin: date) -> Iterable[date]:
    actual = inicio
    while actual <= fin:
        yield actual
        actual += timedelta(days=1)


def _fechas_festivas(calendar_rules: dict[str, Any]) -> set[date]:
    holidays = calendar_rules.get("holidays", {})
    if not holidays.get("enabled", False):
        return set()

    resultado: set[date] = set()
    for elemento in holidays.get("dates", []):
        valor = elemento.get("date") if isinstance(elemento, dict) else elemento
        resultado.add(_convertir_fecha(valor, "calendar.holidays.dates.date"))
    return resultado


def _periodos_vacacionales(
    calendar_rules: dict[str, Any],
) -> list[tuple[date, date]]:
    vacation_rules = calendar_rules.get("vacation_periods", {})
    if not vacation_rules.get("enabled", False):
        return []

    resultado: list[tuple[date, date]] = []
    for periodo in vacation_rules.get("periods", []):
        inicio = _convertir_fecha(
            periodo["start_date"],
            "calendar.vacation_periods.start_date",
        )
        fin = _convertir_fecha(
            periodo["end_date"],
            "calendar.vacation_periods.end_date",
        )
        if fin < inicio:
            raise ValueError(f"Periodo vacacional invalido: {inicio} a {fin}")
        resultado.append((inicio, fin))
    return resultado


def _es_vacacional(fecha: date, periodos: list[tuple[date, date]]) -> bool:
    return any(inicio <= fecha <= fin for inicio, fin in periodos)


def _clasificar_dia(
    fecha: date,
    festivos: set[date],
    day_types: dict[str, str],
) -> tuple[str, bool]:
    es_festivo = fecha in festivos

    if es_festivo or fecha.weekday() == 6:
        return day_types.get("sunday_or_holiday", "D"), es_festivo
    if fecha.weekday() == 5:
        return day_types.get("saturday", "S"), False
    return day_types.get("weekday", "H"), False


def _validar_tipo_dia(tipo_dia: str) -> None:
    if tipo_dia not in {"H", "S", "D"}:
        raise ValueError(
            f"Tipo de dia {tipo_dia!r} invalido. PostgreSQL solo acepta H, S o D."
        )


def _generar_temperaturas(
    fecha: date,
    calendar_rules: dict[str, Any],
    services_rules: dict[str, Any],
    rng: random.Random,
) -> tuple[float, float]:
    mes = MESES[fecha.month]
    temperature_rules = calendar_rules.get("temperature", {})

    if mes not in temperature_rules:
        raise KeyError(f"No existen reglas de temperatura para el mes: {mes}")

    reglas_mes = temperature_rules[mes]
    min_range = reglas_mes["min_c"]
    max_range = reglas_mes["max_c"]

    temp_min = rng.uniform(float(min_range[0]), float(min_range[1]))
    temp_max = rng.uniform(float(max_range[0]), float(max_range[1]))

    # La altitud es opcional y nunca se inserta en PostgreSQL.
    altitude_rules = services_rules.get("altitude", {})
    usar_altitud = (
        calendar_rules.get("adjust_temperature_by_altitude", False)
        and altitude_rules.get("enabled", False)
    )

    if usar_altitud:
        referencia = float(altitude_rules.get("reference_meters", 2600))
        altitud = referencia

        if "min_meters" in altitude_rules and "max_meters" in altitude_rules:
            altitud = rng.uniform(
                float(altitude_rules["min_meters"]),
                float(altitude_rules["max_meters"]),
            )

        cambio_100m = float(
            altitude_rules.get("temperature_change_per_100m", -0.6)
        )
        limite = abs(
            float(altitude_rules.get("maximum_temperature_adjustment_c", 2.5))
        )
        ajuste = ((altitud - referencia) / 100.0) * cambio_100m
        ajuste = max(-limite, min(limite, ajuste))

        temp_min += ajuste
        temp_max += ajuste

    temp_min = round(temp_min, 1)
    temp_max = round(temp_max, 1)

    if temp_max <= temp_min:
        raise ValueError(
            f"Temperaturas invalidas para {fecha}: minima={temp_min}, maxima={temp_max}"
        )

    return temp_min, temp_max


def construir_calendario(
    config: dict[str, Any],
    rules: dict[str, Any],
) -> list[tuple[date, str, bool, bool, float, float, float]]:
    """Construye las filas sin escribir todavía en PostgreSQL."""
    generation = _seccion_generacion(config)

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

    semilla = int(generation.get("seed", generation.get("semilla", 42)))
    rng = random.Random(semilla)

    calendar_rules = rules.get("calendar", {})
    services_rules = rules.get("services", {})
    day_types = calendar_rules.get("day_types", {})
    festivos = _fechas_festivas(calendar_rules)
    vacaciones = _periodos_vacacionales(calendar_rules)
    seasonal_rules = calendar_rules.get("seasonal_factor", {})

    filas = []

    for fecha in _rango_fechas(fecha_inicio, fecha_fin):
        mes = MESES[fecha.month]
        if mes not in seasonal_rules:
            raise KeyError(f"No existe factor estacional para el mes: {mes}")

        tipo_dia, es_festivo = _clasificar_dia(fecha, festivos, day_types)
        _validar_tipo_dia(tipo_dia)

        temp_min, temp_max = _generar_temperaturas(
            fecha,
            calendar_rules,
            services_rules,
            rng,
        )

        factor_estacional = round(float(seasonal_rules[mes]), 4)
        if not 0.5 <= factor_estacional <= 2.0:
            raise ValueError(
                f"Factor estacional fuera del rango permitido para {mes}: "
                f"{factor_estacional}"
            )

        filas.append(
            (
                fecha,
                tipo_dia,
                es_festivo,
                _es_vacacional(fecha, vacaciones),
                temp_min,
                temp_max,
                factor_estacional,
            )
        )

    return filas


def generar_calendario(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    """Genera e inserta el calendario. Devuelve el total de filas procesadas."""
    filas = construir_calendario(config, rules)

    sql = """
        INSERT INTO energia.calendario (
            fecha,
            tipo_dia,
            es_festivo,
            es_vacacional,
            temp_min_c,
            temp_max_c,
            factor_estacional
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fecha) DO UPDATE SET
            tipo_dia = EXCLUDED.tipo_dia,
            es_festivo = EXCLUDED.es_festivo,
            es_vacacional = EXCLUDED.es_vacacional,
            temp_min_c = EXCLUDED.temp_min_c,
            temp_max_c = EXCLUDED.temp_max_c,
            factor_estacional = EXCLUDED.factor_estacional
    """

    try:
        with connection.cursor() as cursor:
            cursor.executemany(sql, filas)
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    festivos = sum(1 for fila in filas if fila[2])
    vacacionales = sum(1 for fila in filas if fila[3])

    print(f"[OK] Calendario generado: {len(filas):,} dias")
    print(f"[OK] Dias festivos: {festivos:,}")
    print(f"[OK] Dias vacacionales: {vacacionales:,}")

    return len(filas)


# Alias uniforme para usarlo desde main.py.
def generar(connection: Any, config: dict[str, Any], rules: dict[str, Any]) -> int:
    return generar_calendario(connection, config, rules)
