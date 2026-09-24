"""
Generador masivo de lecturas para HyperDataSynthetic.

Compatible con Psycopg 3.

Flujo:
1. Carga calendario, medidores, servicios, tipos y perfiles desde PostgreSQL.
2. Carga los eventos que pueden modificar cada lectura.
3. Genera las lecturas de forma secuencial y reproducible.
4. Acumula un lote configurable en memoria.
5. Inserta cada lote mediante PostgreSQL COPY FROM STDIN.
6. Actualiza energia.evento.kwh_desviados al finalizar.

Este archivo no modifica la estructura de la base de datos.
"""

from __future__ import annotations

import csv
import random
import time
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta
from io import StringIO


# ======================================================================
# CONFIGURACION
# ======================================================================


def _seccion_generacion(config):
    """Devuelve la seccion generation o el diccionario principal."""
    generation = config.get("generation")
    return generation if isinstance(generation, dict) else config


def _obtener(config, *nombres):
    """Obtiene un parametro utilizando diferentes nombres posibles."""
    for nombre in nombres:
        if nombre in config:
            return config[nombre]

    raise KeyError(
        "Falta uno de estos parametros: " + ", ".join(nombres)
    )


def _convertir_fecha(valor, nombre):
    """Convierte un valor en una fecha."""
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

    raise TypeError(
        f"{nombre} debe ser una fecha o texto YYYY-MM-DD"
    )


def _config_lecturas(config):
    """Obtiene la configuracion especifica de lecturas."""
    generation = _seccion_generacion(config)
    section = generation.get(
        "readings",
        generation.get("lecturas", {}),
    )
    return section if isinstance(section, dict) else {}


def _config_rendimiento(config):
    """Obtiene la seccion performance."""
    section = config.get("performance", {})
    return section if isinstance(section, dict) else {}


def _iterar_instantes(inicio, fin_exclusivo, minutos):
    """Genera los instantes de lectura dentro de un periodo."""
    actual = inicio
    paso = timedelta(minutes=minutos)

    while actual < fin_exclusivo:
        yield actual
        actual += paso


# ======================================================================
# CARGA DE DATOS DE REFERENCIA
# ======================================================================


def _cargar_calendario(connection, desde, hasta):
    """Carga el calendario del periodo solicitado."""
    sql = """
        SELECT
            fecha,
            tipo_dia,
            temp_min_c,
            temp_max_c,
            factor_estacional
        FROM energia.calendario
        WHERE fecha BETWEEN %s AND %s
        ORDER BY fecha
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (desde, hasta))
        filas = cursor.fetchall()

    calendario = {
        fila[0]: {
            "tipo_dia": str(fila[1]).strip(),
            "temp_min_c": float(fila[2]),
            "temp_max_c": float(fila[3]),
            "factor_estacional": float(fila[4]),
        }
        for fila in filas
    }

    dias_esperados = (hasta - desde).days + 1

    if len(calendario) != dias_esperados:
        raise RuntimeError(
            f"energia.calendario contiene {len(calendario)} dias del periodo, "
            f"pero se esperaban {dias_esperados}. "
            "Ejecuta Calendario_Gen.py primero."
        )

    return calendario


def _cargar_medidores_servicios(connection):
    """Carga medidores, servicios, zonas y tipos de servicio."""
    sql = """
        SELECT
            m.id_medidor,
            m.fecha_instalacion,
            m.fecha_retiro,
            COALESCE(m.multiplicador, 1),
            s.id_tipo_servicio,
            s.ocupacion_estimada,
            s.tiene_solar,
            z.factor_socioeconomico,
            ts.consumo_base_kwh_h,
            ts.factor_dispersion,
            ts.sensibilidad_temp
        FROM energia.medidor AS m
        JOIN energia.servicio AS s
          ON s.id_servicio = m.id_servicio
        JOIN energia.zona AS z
          ON z.id_zona = s.id_zona
        JOIN energia.tipo_servicio AS ts
          ON ts.id_tipo_servicio = s.id_tipo_servicio
        ORDER BY m.id_medidor
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    if not filas:
        raise RuntimeError(
            "No hay medidores disponibles. Ejecuta Servicios_Gen.py y "
            "Dispositivos_Gen.py primero."
        )

    resultado = []

    for fila in filas:
        fecha_instalacion = fila[1]
        fecha_retiro = fila[2]

        if isinstance(fecha_instalacion, datetime):
            fecha_instalacion = fecha_instalacion.date()

        if isinstance(fecha_retiro, datetime):
            fecha_retiro = fecha_retiro.date()

        resultado.append(
            {
                "id_medidor": int(fila[0]),
                "fecha_instalacion": fecha_instalacion,
                "fecha_retiro": fecha_retiro,
                "multiplicador": int(fila[3]),
                "id_tipo_servicio": int(fila[4]),
                "ocupacion_estimada": (
                    int(fila[5]) if fila[5] is not None else None
                ),
                "tiene_solar": bool(fila[6]),
                "factor_socioeconomico": float(fila[7]),
                "consumo_base": float(fila[8]),
                "factor_dispersion": float(fila[9]),
                "sensibilidad_temp": float(fila[10]),
            }
        )

    return resultado


def _cargar_perfiles(connection):
    """Carga los perfiles horarios de consumo."""
    sql = """
        SELECT
            id_tipo_servicio,
            tipo_dia,
            hora,
            factor
        FROM energia.perfil_carga_horaria
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    perfiles = {
        (
            int(fila[0]),
            str(fila[1]).strip(),
            int(fila[2]),
        ): float(fila[3])
        for fila in filas
    }

    if not perfiles:
        raise RuntimeError(
            "energia.perfil_carga_horaria esta vacia."
        )

    return perfiles


def _cargar_eventos(connection):
    """Carga los eventos agrupados por medidor."""
    sql = """
        SELECT
            e.id_evento,
            e.id_medidor,
            e.ts_inicio,
            e.ts_fin,
            e.intensidad,
            te.efecto
        FROM energia.evento AS e
        JOIN energia.tipo_evento AS te
          ON te.id_tipo_evento = e.id_tipo_evento
        ORDER BY e.id_medidor, e.ts_inicio
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    eventos = defaultdict(list)

    for fila in filas:
        eventos[int(fila[1])].append(
            {
                "id_evento": int(fila[0]),
                "inicio": fila[2],
                "fin": fila[3],
                "intensidad": (
                    float(fila[4]) if fila[4] is not None else None
                ),
                "efecto": str(fila[5]),
            }
        )

    return eventos


# ======================================================================
# CALCULO DE CONSUMO
# ======================================================================


def _temperatura_horaria(temp_min, temp_max, hora):
    """Interpolacion simple: minima a las 06:00 y maxima a las 15:00."""
    if 6 <= hora <= 15:
        progreso = (hora - 6) / 9
        return temp_min + (temp_max - temp_min) * progreso

    if hora > 15:
        progreso = (hora - 15) / 15
    else:
        progreso = (hora + 9) / 15

    return temp_max - (temp_max - temp_min) * progreso


def _factor_temperatura(temperatura, sensibilidad, habilitado):
    """Calcula el factor de consumo relacionado con la temperatura."""
    if not habilitado or sensibilidad <= 0:
        return 1.0

    if temperatura < 18.0:
        desviacion = 18.0 - temperatura
    elif temperatura > 24.0:
        desviacion = temperatura - 24.0
    else:
        desviacion = 0.0

    return 1.0 + desviacion * sensibilidad


def _factor_ocupacion(ocupacion):
    """Calcula el factor de consumo relacionado con la ocupacion."""
    if ocupacion is None:
        return 1.0

    return max(
        0.75,
        min(1.45, 1.0 + (ocupacion - 4) * 0.08),
    )


def _buscar_evento(eventos_medidor, instante):
    """Busca el evento activo para un instante."""
    for evento in eventos_medidor:
        if evento["inicio"] <= instante < evento["fin"]:
            return evento

        if evento["inicio"] > instante:
            break

    return None


def _aplicar_evento(consumo_real, evento, ultimo_reportado):
    """Aplica el efecto de un evento al consumo reportado."""
    if evento is None:
        return consumo_real, None

    efecto = evento["efecto"]
    intensidad = evento["intensidad"]
    id_evento = evento["id_evento"]

    if efecto == "INCREMENTO":
        factor = intensidad if intensidad is not None else 1.0
        return consumo_real * factor, id_evento

    if efecto == "REDUCCION":
        factor = intensidad if intensidad is not None else 1.0
        return consumo_real * factor, id_evento

    if efecto == "CONGELAMIENTO":
        valor = ultimo_reportado if ultimo_reportado is not None else 0.0
        return valor, id_evento

    if efecto == "NULIFICACION":
        return None, id_evento

    raise ValueError(
        f"Efecto de evento desconocido: {efecto}"
    )


def _generar_filas(
    medidores,
    calendario,
    perfiles,
    eventos,
    periodo_inicio,
    periodo_fin_exclusivo,
    intervalo_min,
    rules,
    rng,
):
    """Genera secuencialmente las lecturas."""
    consumption_rules = rules.get("consumption", {})
    solar_rules = rules.get("solar", {})

    random_rules = consumption_rules.get("random_factor", {})
    random_min = float(random_rules.get("min", 0.90))
    random_max = float(random_rules.get("max", 1.10))
    minimum_kwh = float(consumption_rules.get("minimum_kwh", 0.0))

    use_socio = bool(
        consumption_rules.get("use_socioeconomic_factor", True)
    )
    use_seasonal = bool(
        consumption_rules.get("use_seasonal_factor", True)
    )
    use_profile = bool(
        consumption_rules.get("use_hourly_profile", True)
    )
    use_temperature = bool(
        consumption_rules.get("use_temperature_factor", True)
    )

    solar_start = int(solar_rules.get("start_hour", 9))
    solar_end = int(solar_rules.get("end_hour", 17))
    solar_reduction = solar_rules.get("reduction", {})
    solar_min = float(solar_reduction.get("min", 0.15))
    solar_max = float(solar_reduction.get("max", 0.45))

    for medidor in medidores:
        inicio_medidor = max(
            periodo_inicio.date(),
            medidor["fecha_instalacion"],
        )

        inicio = datetime.combine(inicio_medidor, dt_time.min)
        fin_medidor_exclusivo = periodo_fin_exclusivo

        if medidor["fecha_retiro"] is not None:
            retiro_exclusivo = datetime.combine(
                medidor["fecha_retiro"],
                dt_time.min,
            )
            fin_medidor_exclusivo = min(
                fin_medidor_exclusivo,
                retiro_exclusivo,
            )

        if inicio >= fin_medidor_exclusivo:
            continue

        ultimo_reportado = None
        dispersion = medidor["factor_dispersion"]
        factor_individual = max(
            0.20,
            rng.normalvariate(1.0, dispersion / 3.0),
        )

        for instante in _iterar_instantes(
            inicio,
            fin_medidor_exclusivo,
            intervalo_min,
        ):
            fecha_actual = instante.date()

            if fecha_actual not in calendario:
                raise KeyError(
                    f"No existe calendario para la fecha {fecha_actual}"
                )

            dia = calendario[fecha_actual]
            clave_perfil = (
                medidor["id_tipo_servicio"],
                str(dia["tipo_dia"]).strip(),
                instante.hour,
            )

            if use_profile:
                if clave_perfil not in perfiles:
                    raise KeyError(
                        f"No existe perfil horario para {clave_perfil}"
                    )
                factor_perfil = perfiles[clave_perfil]
            else:
                factor_perfil = 1.0

            temperatura = _temperatura_horaria(
                dia["temp_min_c"],
                dia["temp_max_c"],
                instante.hour,
            )

            consumo_real = medidor["consumo_base"]
            consumo_real *= factor_perfil
            consumo_real *= factor_individual
            consumo_real *= _factor_ocupacion(
                medidor["ocupacion_estimada"]
            )

            if use_socio:
                consumo_real *= medidor["factor_socioeconomico"]

            if use_seasonal:
                consumo_real *= dia["factor_estacional"]

            consumo_real *= _factor_temperatura(
                temperatura,
                medidor["sensibilidad_temp"],
                use_temperature,
            )
            consumo_real *= rng.uniform(random_min, random_max)

            if (
                medidor["tiene_solar"]
                and solar_start <= instante.hour <= solar_end
            ):
                consumo_real *= 1.0 - rng.uniform(
                    solar_min,
                    solar_max,
                )

            consumo_real *= intervalo_min / 60.0
            consumo_real *= medidor["multiplicador"]
            consumo_real = round(
                max(minimum_kwh, consumo_real),
                4,
            )

            evento = _buscar_evento(
                eventos.get(medidor["id_medidor"], []),
                instante,
            )
            consumo_reportado, id_evento = _aplicar_evento(
                consumo_real,
                evento,
                ultimo_reportado,
            )

            if consumo_reportado is not None:
                consumo_reportado = round(
                    max(minimum_kwh, consumo_reportado),
                    4,
                )
                ultimo_reportado = consumo_reportado

            yield (
                medidor["id_medidor"],
                instante,
                consumo_reportado,
                consumo_real,
                id_evento,
            )


# ======================================================================
# COPY Y ACTUALIZACION DE EVENTOS
# ======================================================================


def _copiar_lote(connection, lote):
    """Inserta un lote con COPY FROM STDIN usando Psycopg 3."""
    if not lote:
        return

    buffer = StringIO()
    writer = csv.writer(
        buffer,
        delimiter="\t",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )

    for id_medidor, instante, consumo, consumo_real, id_evento in lote:
        writer.writerow(
            (
                id_medidor,
                instante.strftime("%Y-%m-%d %H:%M:%S"),
                r"\N" if consumo is None else f"{consumo:.4f}",
                f"{consumo_real:.4f}",
                r"\N" if id_evento is None else id_evento,
            )
        )

    contenido = buffer.getvalue()

    sql = r"""
        COPY energia.lectura (
            id_medidor,
            ts,
            consumo_kwh,
            consumo_real_kwh,
            id_evento
        )
        FROM STDIN
        WITH (
            FORMAT CSV,
            DELIMITER E'\t',
            NULL '\N'
        )
    """

    with connection.cursor() as cursor:
        with cursor.copy(sql) as copy:
            copy.write(contenido)


def _actualizar_kwh_desviados(connection):
    """Actualiza energia.evento.kwh_desviados."""
    sql = """
        UPDATE energia.evento AS e
        SET kwh_desviados = calculo.kwh_desviados
        FROM (
            SELECT
                id_evento,
                ROUND(
                    SUM(
                        ABS(
                            consumo_real_kwh
                            - COALESCE(consumo_kwh, consumo_real_kwh)
                        )
                    ),
                    4
                ) AS kwh_desviados
            FROM energia.lectura
            WHERE id_evento IS NOT NULL
            GROUP BY id_evento
        ) AS calculo
        WHERE calculo.id_evento = e.id_evento
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)


# ======================================================================
# GENERADOR PUBLICO
# ======================================================================


def generar_lecturas(connection, config, rules):
    """Genera e inserta las lecturas del periodo configurado."""
    generation = _seccion_generacion(config)
    readings_config = _config_lecturas(config)
    performance_config = _config_rendimiento(config)

    fecha_inicio = _convertir_fecha(
        _obtener(
            generation,
            "start_date",
            "fecha_inicial",
            "fecha_desde",
        ),
        "fecha inicial",
    )
    fecha_fin = _convertir_fecha(
        _obtener(
            generation,
            "end_date",
            "fecha_final",
            "fecha_hasta",
        ),
        "fecha final",
    )

    if fecha_fin < fecha_inicio:
        raise ValueError(
            "La fecha final no puede ser anterior a la fecha inicial"
        )

    intervalo_min = int(
        generation.get(
            "reading_interval_minutes",
            generation.get(
                "intervalo_min",
                generation.get("interval_minutes", 60),
            ),
        )
    )

    if intervalo_min not in {5, 15, 30, 60}:
        raise ValueError(
            "El intervalo debe ser 5, 15, 30 o 60 minutos"
        )

    batch_size = int(
        readings_config.get(
            "batch_size",
            performance_config.get(
                "batch_size",
                generation.get("batch_size", 100_000),
            ),
        )
    )

    if batch_size <= 0:
        raise ValueError("batch_size debe ser mayor que cero")

    replace_existing = bool(
        readings_config.get("replace_existing", False)
    )
    commit_per_batch = bool(
        readings_config.get("commit_per_batch", True)
    )

    semilla = int(
        generation.get("seed", generation.get("semilla", 42))
    )
    rng = random.Random(
        int(readings_config.get("seed", semilla + 4000))
    )

    periodo_inicio = datetime.combine(fecha_inicio, dt_time.min)
    periodo_fin_exclusivo = datetime.combine(
        fecha_fin + timedelta(days=1),
        dt_time.min,
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM energia.lectura
            WHERE ts >= %s
              AND ts < %s
            """,
            (periodo_inicio, periodo_fin_exclusivo),
        )
        fila_conteo = cursor.fetchone()
        existentes = int(fila_conteo[0]) if fila_conteo else 0

    if existentes and not replace_existing:
        raise RuntimeError(
            f"Ya existen {existentes:,} lecturas para el periodo. "
            "Configura generation.readings.replace_existing: true "
            "o limpia el periodo manualmente."
        )

    calendario = _cargar_calendario(
        connection,
        fecha_inicio,
        fecha_fin,
    )
    medidores = _cargar_medidores_servicios(connection)
    perfiles = _cargar_perfiles(connection)
    eventos = _cargar_eventos(connection)

    total_eventos = sum(len(lista) for lista in eventos.values())

    print(f"[OK] Dias cargados: {len(calendario):,}")
    print(f"[OK] Medidores cargados: {len(medidores):,}")
    print(f"[OK] Perfiles cargados: {len(perfiles):,}")
    print(f"[OK] Eventos cargados: {total_eventos:,}")
    print(f"[OK] Tamano de lote: {batch_size:,}")

    inicio_cronometro = time.perf_counter()
    lote = []
    total = 0
    numero_lote = 0

    try:
        if existentes and replace_existing:
            print(
                f"[INFO] Eliminando {existentes:,} lecturas existentes..."
            )

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM energia.lectura
                    WHERE ts >= %s
                      AND ts < %s
                    """,
                    (periodo_inicio, periodo_fin_exclusivo),
                )

            connection.commit()
            print("[OK] Lecturas existentes eliminadas")

        filas = _generar_filas(
            medidores,
            calendario,
            perfiles,
            eventos,
            periodo_inicio,
            periodo_fin_exclusivo,
            intervalo_min,
            rules,
            rng,
        )

        for fila in filas:
            lote.append(fila)

            if len(lote) >= batch_size:
                _copiar_lote(connection, lote)
                total += len(lote)
                numero_lote += 1

                if commit_per_batch:
                    connection.commit()

                transcurrido = time.perf_counter() - inicio_cronometro
                velocidad = total / transcurrido if transcurrido else 0

                print(
                    f"[LOTE {numero_lote:03d}] "
                    f"{total:,} lecturas | "
                    f"{velocidad:,.0f} lecturas/s"
                )
                lote.clear()

        if lote:
            _copiar_lote(connection, lote)
            total += len(lote)
            numero_lote += 1

            if commit_per_batch:
                connection.commit()

            transcurrido = time.perf_counter() - inicio_cronometro
            velocidad = total / transcurrido if transcurrido else 0

            print(
                f"[LOTE {numero_lote:03d}] "
                f"{total:,} lecturas | "
                f"{velocidad:,.0f} lecturas/s"
            )
            lote.clear()

        if not commit_per_batch:
            connection.commit()

        _actualizar_kwh_desviados(connection)
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    transcurrido = time.perf_counter() - inicio_cronometro
    velocidad = total / transcurrido if transcurrido else 0

    print(f"[OK] Lecturas generadas: {total:,}")
    print(f"[OK] Lotes procesados: {numero_lote:,}")
    print(f"[OK] Tiempo total: {transcurrido:,.2f} segundos")
    print(f"[OK] Velocidad: {velocidad:,.0f} lecturas/segundo")
    print("[OK] kwh_desviados actualizado en energia.evento")

    return total


# ======================================================================
# ALIAS UNIFORME PARA MAIN.PY
# ======================================================================


def generar(connection, config, rules):
    """Alias uniforme para ejecutar el generador."""
    return generar_lecturas(connection, config, rules)
