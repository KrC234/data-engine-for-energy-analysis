"""Generador de eventos sintéticos de HyperDataSynthetic.

Responsabilidad:
- Lee medidores y sus vigencias desde energia.medidor.
- Lee reglas de anomalías desde energia.tipo_evento.
- Genera eventos reproducibles dentro de la vigencia de cada medidor.
- Evita traslapes de eventos para un mismo medidor.
- Inserta los eventos en energia.evento.

Convención temporal:
- fecha_instalacion es inclusiva.
- fecha_retiro es exclusiva.
- Un evento cumple: instalacion <= ts_inicio < ts_fin <= retiro.

Notas:
- No modifica la estructura de PostgreSQL.
- kwh_desviados inicia en 0. Lecturas_Gen.py podrá calcularlo después.
- Usa la tasa mensual almacenada en energia.tipo_evento.
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta
from typing import Any


# ======================================================================
# CONFIGURACION
# ======================================================================


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


def _config_eventos(config: dict[str, Any]) -> dict[str, Any]:
    generation = _seccion_generacion(config)
    eventos = generation.get("events", generation.get("eventos", {}))
    return eventos if isinstance(eventos, dict) else {}


# ======================================================================
# UTILIDADES ALEATORIAS
# ======================================================================


def _poisson(media: float, rng: random.Random) -> int:
    """Genera un entero Poisson sin dependencias externas."""
    if media <= 0:
        return 0

    limite = math.exp(-media)
    producto = 1.0
    cantidad = 0

    while producto > limite:
        cantidad += 1
        producto *= rng.random()

    return cantidad - 1


def _traslapa(
    inicio: datetime,
    fin: datetime,
    intervalos: list[tuple[datetime, datetime]],
) -> bool:
    return any(
        inicio < existente_fin and fin > existente_inicio
        for existente_inicio, existente_fin in intervalos
    )


def _elegir_intervalo(
    periodo_inicio: datetime,
    periodo_fin_exclusivo: datetime,
    duracion_horas: int,
    intervalos_ocupados: list[tuple[datetime, datetime]],
    rng: random.Random,
    intentos_maximos: int,
) -> tuple[datetime, datetime] | None:
    """Busca un intervalo horario válido, completo y sin traslapes."""
    duracion = timedelta(hours=duracion_horas)
    ultimo_inicio = periodo_fin_exclusivo - duracion

    if ultimo_inicio < periodo_inicio:
        return None

    horas_disponibles = int(
        (ultimo_inicio - periodo_inicio).total_seconds() // 3600
    )

    for _ in range(intentos_maximos):
        desplazamiento = rng.randint(0, horas_disponibles)
        inicio = periodo_inicio + timedelta(hours=desplazamiento)
        fin = inicio + duracion

        if fin <= periodo_fin_exclusivo and not _traslapa(
            inicio, fin, intervalos_ocupados
        ):
            return inicio, fin

    return None


# ======================================================================
# CONSULTAS
# ======================================================================


def _cargar_medidores(connection: Any) -> list[dict[str, Any]]:
    """Carga cada medidor junto con su intervalo de vigencia."""
    sql = """
        SELECT
            id_medidor,
            fecha_instalacion,
            fecha_retiro
        FROM energia.medidor
        ORDER BY id_medidor
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    medidores: list[dict[str, Any]] = []
    for id_medidor, fecha_instalacion, fecha_retiro in filas:
        if fecha_instalacion is None:
            raise RuntimeError(
                f"El medidor {id_medidor} no tiene fecha_instalacion"
            )

        medidores.append(
            {
                "id_medidor": int(id_medidor),
                "fecha_instalacion": _convertir_fecha(
                    fecha_instalacion, "fecha_instalacion"
                ),
                "fecha_retiro": (
                    _convertir_fecha(fecha_retiro, "fecha_retiro")
                    if fecha_retiro is not None
                    else None
                ),
            }
        )

    return medidores


def _cargar_tipos_evento(connection: Any) -> list[dict[str, Any]]:
    sql = """
        SELECT
            id_tipo_evento,
            clave,
            efecto,
            duracion_min_h,
            duracion_max_h,
            intensidad_min,
            intensidad_max,
            tasa_por_medidor_mes
        FROM energia.tipo_evento
        ORDER BY id_tipo_evento
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    tipos = []
    for fila in filas:
        tipos.append(
            {
                "id_tipo_evento": fila[0],
                "clave": fila[1],
                "efecto": fila[2],
                "duracion_min_h": int(fila[3]),
                "duracion_max_h": int(fila[4]),
                "intensidad_min": (
                    float(fila[5]) if fila[5] is not None else None
                ),
                "intensidad_max": (
                    float(fila[6]) if fila[6] is not None else None
                ),
                "tasa_por_medidor_mes": float(fila[7]),
            }
        )

    return tipos


def _contar_eventos(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM energia.evento")
        return int(cursor.fetchone()[0])


def _siguiente_id(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(MAX(id_evento), 0) + 1 FROM energia.evento"
        )
        return int(cursor.fetchone()[0])


# ======================================================================
# CONSTRUCCION
# ======================================================================


def construir_eventos(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> list[tuple[int, int, int, datetime, datetime, float | None, float]]:
    """Construye eventos dentro de la vigencia real de cada medidor."""
    del rules

    generation = _seccion_generacion(config)
    events_config = _config_eventos(config)

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

    corrida_inicio = datetime.combine(fecha_inicio, time.min)
    corrida_fin_exclusivo = datetime.combine(
        fecha_fin + timedelta(days=1), time.min
    )

    semilla_base = int(generation.get("seed", generation.get("semilla", 42)))
    semilla_eventos = int(events_config.get("seed", semilla_base + 3000))
    rng = random.Random(semilla_eventos)

    intentos_maximos = int(events_config.get("max_placement_attempts", 100))
    if intentos_maximos <= 0:
        raise ValueError("events.max_placement_attempts debe ser mayor que cero")

    medidores = _cargar_medidores(connection)
    tipos_evento = _cargar_tipos_evento(connection)

    if not medidores:
        raise RuntimeError(
            "No hay medidores en energia.medidor. Ejecuta Dispositivos_Gen.py primero."
        )

    if not tipos_evento:
        raise RuntimeError(
            "No hay tipos de evento en energia.tipo_evento. Carga los catalogos primero."
        )

    id_evento = _siguiente_id(connection)
    eventos = []
    ocupados: dict[int, list[tuple[datetime, datetime]]] = {
        medidor["id_medidor"]: [] for medidor in medidores
    }

    for medidor in medidores:
        id_medidor = medidor["id_medidor"]

        instalacion = datetime.combine(
            medidor["fecha_instalacion"], time.min
        )
        retiro = (
            datetime.combine(medidor["fecha_retiro"], time.min)
            if medidor["fecha_retiro"] is not None
            else corrida_fin_exclusivo
        )

        # Intersección entre la corrida y la vigencia del medidor.
        periodo_inicio = max(corrida_inicio, instalacion)
        periodo_fin_exclusivo = min(corrida_fin_exclusivo, retiro)

        if periodo_fin_exclusivo <= periodo_inicio:
            continue

        dias_vigentes = (
            periodo_fin_exclusivo - periodo_inicio
        ).total_seconds() / 86400.0
        meses_equivalentes = dias_vigentes / 30.0

        for tipo in tipos_evento:
            media = tipo["tasa_por_medidor_mes"] * meses_equivalentes
            cantidad = _poisson(media, rng)

            for _ in range(cantidad):
                duracion = rng.randint(
                    tipo["duracion_min_h"], tipo["duracion_max_h"]
                )

                intervalo = _elegir_intervalo(
                    periodo_inicio,
                    periodo_fin_exclusivo,
                    duracion,
                    ocupados[id_medidor],
                    rng,
                    intentos_maximos,
                )

                if intervalo is None:
                    continue

                inicio, fin = intervalo

                if (
                    tipo["intensidad_min"] is not None
                    and tipo["intensidad_max"] is not None
                ):
                    intensidad = round(
                        rng.uniform(
                            tipo["intensidad_min"],
                            tipo["intensidad_max"],
                        ),
                        3,
                    )
                else:
                    intensidad = None

                eventos.append(
                    (
                        id_evento,
                        id_medidor,
                        tipo["id_tipo_evento"],
                        inicio,
                        fin,
                        intensidad,
                        0.0,
                    )
                )

                ocupados[id_medidor].append((inicio, fin))
                ocupados[id_medidor].sort()
                id_evento += 1

    eventos.sort(key=lambda fila: (fila[1], fila[3], fila[0]))
    return eventos


# ======================================================================
# INSERCION
# ======================================================================


def generar_eventos(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    """Genera e inserta eventos. Devuelve el total insertado."""
    events_config = _config_eventos(config)
    reemplazar = bool(events_config.get("replace_existing", False))
    batch_size = int(events_config.get("batch_size", 5000))

    if batch_size <= 0:
        raise ValueError("events.batch_size debe ser mayor que cero")

    existentes = _contar_eventos(connection)

    if existentes and not reemplazar:
        raise RuntimeError(
            f"energia.evento ya contiene {existentes:,} filas. "
            "Para evitar duplicados, deja la tabla vacia o configura "
            "events.replace_existing: true."
        )

    try:
        if reemplazar and existentes:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM energia.evento")

        eventos = construir_eventos(connection, config, rules)

        sql = """
            INSERT INTO energia.evento (
                id_evento,
                id_medidor,
                id_tipo_evento,
                ts_inicio,
                ts_fin,
                intensidad,
                kwh_desviados
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        with connection.cursor() as cursor:
            for inicio in range(0, len(eventos), batch_size):
                lote = eventos[inicio:inicio + batch_size]
                cursor.executemany(sql, lote)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    print(f"[OK] Eventos generados: {len(eventos):,}")
    print(f"[OK] Medidores evaluados: {len(_cargar_medidores(connection)):,}")
    print("[OK] Eventos dentro de la vigencia de cada medidor")
    print("[OK] Eventos sin traslapes por medidor")
    print("[OK] kwh_desviados inicia en 0 y se calcula con las lecturas")

    return len(eventos)


# Alias uniforme para main.py.
def generar(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    return generar_eventos(connection, config, rules)
