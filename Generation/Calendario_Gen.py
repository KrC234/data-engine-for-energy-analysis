"""
    GENERADOR DE CALENDARIO (Generation/Calendario_Gen.py)

    Llena energia.calendario para el rango de fechas de la corrida
    (generation.date_start .. generation.date_end de config/generation.yaml).

    Reglas (config/rules.yaml -> calendar):
      - temperature.<mes>.min_c/max_c : rangos por mes
      - seasonal_factor.<mes>          : factor estacional
      - holidays.dates                 : festivos (tipo de dia D)
      - vacation_periods.periods       : periodos vacacionales
      - adjust_temperature_by_altitude : ajuste por altitud sintetica

    Columnas (01_esquema.sql):
      fecha, tipo_dia, es_festivo, es_vacacional, temp_min_c,
      temp_max_c, factor_estacional
"""

import random

from datetime import date, timedelta


def _dias_entre(inicio, fin):
    delta = (fin - inicio).days
    for i in range(delta + 1):
        yield inicio + timedelta(days=i)


def _a_fecha(texto):
    anio, mes, dia = texto.split("-")
    return date(int(anio), int(mes), int(dia))


def _ajuste_altitud(rules):
    """Ajuste de temperatura por altitud sintetica (grados C)."""
    alt = rules["services"]["altitude"]
    altitud = random.uniform(alt["min_meters"], alt["max_meters"])
    cambio = alt["temperature_change_per_100m"]
    ref = alt["reference_meters"]
    ajuste = (altitud - ref) / 100.0 * cambio
    limite = alt["maximum_temperature_adjustment_c"]
    return max(-limite, min(limite, ajuste))


def generar_calendario(connection, config, rules):
    """
    Genera las filas de energia.calendario y las inserta por COPY.

    Devuelve la lista de dicts (la consume Lecturas_Gen).
    """
    fecha_desde = config["generation"]["date_start"]
    fecha_hasta = config["generation"]["date_end"]
    reglas_cal = rules["calendar"]

    # --- Reglas ---
    dias_festivos = {
        _a_fecha(item["date"]) for item in reglas_cal["holidays"]["dates"]
    }
    periodos_vacacionales = [
        (_a_fecha(p["start_date"]), _a_fecha(p["end_date"]))
        for p in reglas_cal["vacation_periods"]["periods"]
    ]
    rangos_mes = {}
    for mes, datos in reglas_cal["temperature"].items():
        mes_num = {
            "january": 1, "february": 2, "march": 3,
            "april": 4, "may": 5, "june": 6, "july": 7,
            "august": 8, "september": 9, "october": 10,
            "november": 11, "december": 12,
        }[mes]
        rangos_mes[mes_num] = {
            "min_c": datos["min_c"],
            "max_c": datos["max_c"],
        }
    estacional_mes = {
        "january": 1, "february": 2, "march": 3,
        "april": 4, "may": 5, "june": 6, "july": 7,
        "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }
    # factors_estacionales reales
    estacional = {}
    factores = reglas_cal.get("seasonal_factor") or {}
    for mes, factor in factores.items():
        estacional[estacional_mes[mes]] = factor

    ajustar_temp = reglas_cal.get("adjust_temperature_by_altitude", False)

    filas = []
    calendario = []

    for fecha in _dias_entre(fecha_desde, fecha_hasta):
        # Tipo de dia: festivo > domingo > sabado > habil
        if fecha in dias_festivos:
            tipo_dia = "D"
        elif fecha.weekday() == 6:
            tipo_dia = "D"
        elif fecha.weekday() == 5:
            tipo_dia = "S"
        else:
            tipo_dia = "H"

        es_vacacional = any(
            ini <= fecha <= fin for ini, fin in periodos_vacacionales
        )

        # Temperatura: rango del mes + ajuste por altitud
        rango = rangos_mes.get(fecha.month, {"min_c": [5, 10], "max_c": [20, 25]})
        tmin = random.uniform(rango["min_c"][0], rango["min_c"][1])
        tmax = random.uniform(rango["max_c"][0], rango["max_c"][1])

        if ajustar_temp:
            ajuste = _ajuste_altitud(rules)
            tmin += ajuste
            tmax += ajuste

        tmin = round(max(tmin, -5.0), 1)
        tmax = round(min(tmax, 40.0), 1)
        if tmax <= tmin:  # respetar CHECK temp_max_c > temp_min_c
            tmax = tmin + 1.0

        factor_est = estacional.get(fecha.month, 1.0)

        filas.append(
            [
                fecha.isoformat(),
                tipo_dia,
                1 if fecha in dias_festivos else 0,
                1 if es_vacacional else 0,
                tmin,
                tmax,
                factor_est,
            ]
        )
        calendario.append(
            {
                "fecha": fecha,
                "tipo_dia": tipo_dia,
                "es_festivo": fecha in dias_festivos,
                "es_vacacional": es_vacacional,
                "temp_min": tmin,
                "temp_max": tmax,
                "temp_media": (tmin + tmax) / 2.0,
                "factor_estacional": factor_est,
            }
        )

    from database.insertar import copy_lote

    copy_lote(
        connection,
        "calendario",
        [
            "fecha",
            "tipo_dia",
            "es_festivo",
            "es_vacacional",
            "temp_min_c",
            "temp_max_c",
            "factor_estacional",
        ],
        filas,
        etiqueta="Calendario",
    )
    connection.commit()

    return calendario