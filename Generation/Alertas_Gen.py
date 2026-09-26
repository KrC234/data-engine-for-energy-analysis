"""Generador de alertas sintéticas de HyperDataSynthetic.

Responsabilidad:
- Lee eventos reales desde energia.evento.
- Usa prob_deteccion de energia.tipo_evento para decidir si cada evento
  produce una alerta.
- Permite clasificaciones incorrectas y falsas alarmas controladas.
- Genera prioridad, momento de deteccion, cierre y resultado.
- Respeta la vigencia individual de cada medidor.
- Inserta las filas en energia.alerta sin modificar la estructura de la base.

Convencion temporal:
- fecha_instalacion es inclusiva.
- fecha_retiro es exclusiva.
- Una alerta cumple: instalacion <= ts_generacion < retiro.

Orden recomendado:
    Eventos_Gen.py -> Lecturas_Gen.py -> Alertas_Gen.py
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
    generation = config.get("generation")
    return generation if isinstance(generation, dict) else config


def _config_alertas(config: dict[str, Any]) -> dict[str, Any]:
    generation = _seccion_generacion(config)
    section = generation.get("alerts", generation.get("alertas", {}))
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


def _probabilidad(valor: Any, nombre: str) -> float:
    numero = float(valor)
    if not 0.0 <= numero <= 1.0:
        raise ValueError(f"{nombre} debe estar entre 0 y 1")
    return numero


# ======================================================================
# ALEATORIEDAD REPRODUCIBLE
# ======================================================================


def _poisson(media: float, rng: random.Random) -> int:
    """Genera una cantidad Poisson sin dependencias externas."""
    if media <= 0:
        return 0

    limite = math.exp(-media)
    producto = 1.0
    cantidad = 0

    while producto > limite:
        cantidad += 1
        producto *= rng.random()

    return cantidad - 1


def _elegir_distinto(
    valores: list[int],
    actual: int,
    rng: random.Random,
) -> int:
    alternativas = [valor for valor in valores if valor != actual]
    return rng.choice(alternativas) if alternativas else actual


def _instante_aleatorio(
    inicio: datetime,
    fin_exclusivo: datetime,
    rng: random.Random,
) -> datetime | None:
    """Elige una hora alineada dentro de [inicio, fin_exclusivo)."""
    horas = int((fin_exclusivo - inicio).total_seconds() // 3600)
    if horas <= 0:
        return None
    return inicio + timedelta(hours=rng.randrange(horas))


# ======================================================================
# CONSULTAS
# ======================================================================


def _cargar_tipos_evento(connection: Any) -> dict[int, dict[str, Any]]:
    sql = """
        SELECT
            id_tipo_evento,
            clave,
            efecto,
            duracion_min_h,
            duracion_max_h,
            prob_deteccion
        FROM energia.tipo_evento
        ORDER BY id_tipo_evento
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    if not filas:
        raise RuntimeError(
            "energia.tipo_evento esta vacia. Carga los catalogos primero."
        )

    return {
        int(fila[0]): {
            "id_tipo_evento": int(fila[0]),
            "clave": fila[1],
            "efecto": fila[2],
            "duracion_min_h": int(fila[3]),
            "duracion_max_h": int(fila[4]),
            "prob_deteccion": float(fila[5]),
        }
        for fila in filas
    }


def _cargar_eventos(connection: Any) -> list[dict[str, Any]]:
    sql = """
        SELECT
            id_evento,
            id_medidor,
            id_tipo_evento,
            ts_inicio,
            ts_fin,
            intensidad,
            kwh_desviados
        FROM energia.evento
        ORDER BY ts_inicio, id_evento
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    if not filas:
        raise RuntimeError(
            "energia.evento esta vacia. Ejecuta Eventos_Gen.py primero."
        )

    return [
        {
            "id_evento": int(fila[0]),
            "id_medidor": int(fila[1]),
            "id_tipo_evento": int(fila[2]),
            "ts_inicio": fila[3],
            "ts_fin": fila[4],
            "intensidad": float(fila[5]) if fila[5] is not None else None,
            "kwh_desviados": float(fila[6]),
        }
        for fila in filas
    ]


def _cargar_medidores(connection: Any) -> list[dict[str, Any]]:
    """Carga medidores con su vigencia para generar falsos positivos validos."""
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


def _contar_alertas(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM energia.alerta")
        return int(cursor.fetchone()[0])


def _siguiente_id(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(MAX(id_alerta), 0) + 1 FROM energia.alerta"
        )
        return int(cursor.fetchone()[0])


# ======================================================================
# REGLAS DE ALERTA
# ======================================================================


def _prioridad(
    tipo: dict[str, Any],
    duracion_horas: float,
    kwh_desviados: float,
) -> int:
    """Devuelve prioridad 1 (maxima) a 4 (baja)."""
    efecto = tipo["efecto"]

    if efecto == "INCREMENTO" and (
        kwh_desviados >= 100 or duracion_horas >= 24
    ):
        return 1
    if efecto in {"CONGELAMIENTO", "NULIFICACION"}:
        return 2
    if efecto == "REDUCCION" and duracion_horas >= 72:
        return 2
    if duracion_horas >= 12 or kwh_desviados >= 25:
        return 3
    return 4


def _retraso_deteccion_horas(
    tipo: dict[str, Any],
    duracion_horas: float,
    rng: random.Random,
) -> float:
    """Los efectos evidentes se detectan antes que los prolongados/sutiles."""
    efecto = tipo["efecto"]

    if efecto == "NULIFICACION":
        maximo = min(2.0, duracion_horas)
    elif efecto == "INCREMENTO":
        maximo = min(4.0, duracion_horas)
    elif efecto == "CONGELAMIENTO":
        maximo = min(12.0, duracion_horas)
    else:
        maximo = min(48.0, duracion_horas)

    return rng.uniform(0.25, max(0.25, maximo))


def _cerrar_alerta(
    ts_generacion: datetime,
    periodo_fin_exclusivo: datetime,
    prioridad: int,
    prob_abierta: float,
    prob_no_concluyente: float,
    es_falsa: bool,
    rng: random.Random,
) -> tuple[datetime | None, str | None]:
    if rng.random() < prob_abierta:
        return None, None

    horas_base = {1: 6, 2: 12, 3: 24, 4: 48}[prioridad]
    horas_cierre = rng.uniform(horas_base * 0.5, horas_base * 2.0)
    ts_cierre = ts_generacion + timedelta(hours=horas_cierre)

    if ts_cierre >= periodo_fin_exclusivo:
        return None, None

    if rng.random() < prob_no_concluyente:
        resultado = "NO_CONCLUYENTE"
    elif es_falsa:
        resultado = "FALSO_POSITIVO"
    else:
        resultado = "CONFIRMADA"

    return ts_cierre, resultado


# ======================================================================
# CONSTRUCCION
# ======================================================================


def construir_alertas(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> list[
    tuple[
        int,
        int | None,
        int,
        int,
        datetime,
        int,
        datetime | None,
        str | None,
    ]
]:
    """Construye alertas respetando la vigencia de cada medidor."""
    del rules

    generation = _seccion_generacion(config)
    alert_config = _config_alertas(config)

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

    periodo_inicio = datetime.combine(fecha_inicio, time.min)
    periodo_fin_exclusivo = datetime.combine(
        fecha_fin + timedelta(days=1), time.min
    )

    semilla_base = int(generation.get("seed", generation.get("semilla", 42)))
    semilla = int(alert_config.get("seed", semilla_base + 5000))
    rng = random.Random(semilla)

    misclassification_rate = _probabilidad(
        alert_config.get("misclassification_rate", 0.08),
        "alerts.misclassification_rate",
    )
    false_positive_rate = float(
        alert_config.get("false_positive_rate_per_meter_month", 0.03)
    )
    if false_positive_rate < 0:
        raise ValueError(
            "alerts.false_positive_rate_per_meter_month no puede ser negativa"
        )

    open_probability = _probabilidad(
        alert_config.get("open_probability", 0.04),
        "alerts.open_probability",
    )
    inconclusive_probability = _probabilidad(
        alert_config.get("inconclusive_probability", 0.06),
        "alerts.inconclusive_probability",
    )

    tipos = _cargar_tipos_evento(connection)
    eventos = _cargar_eventos(connection)
    medidores = _cargar_medidores(connection)
    ids_tipo = sorted(tipos)

    if not medidores:
        raise RuntimeError("energia.medidor esta vacia.")

    vigencia_por_medidor = {
        medidor["id_medidor"]: medidor for medidor in medidores
    }

    id_alerta = _siguiente_id(connection)
    alertas = []

    # Alertas asociadas a eventos reales. Un evento valido ya esta contenido
    # en la vigencia de su medidor; se conserva una verificacion defensiva.
    for evento in eventos:
        tipo_real = tipos[evento["id_tipo_evento"]]

        if rng.random() > tipo_real["prob_deteccion"]:
            continue

        medidor = vigencia_por_medidor.get(evento["id_medidor"])
        if medidor is None:
            raise RuntimeError(
                f"El evento {evento['id_evento']} referencia un medidor inexistente"
            )

        instalacion = datetime.combine(
            medidor["fecha_instalacion"], time.min
        )
        retiro = (
            datetime.combine(medidor["fecha_retiro"], time.min)
            if medidor["fecha_retiro"] is not None
            else periodo_fin_exclusivo
        )
        fin_vigencia = min(periodo_fin_exclusivo, retiro)

        duracion_horas = (
            evento["ts_fin"] - evento["ts_inicio"]
        ).total_seconds() / 3600.0

        retraso = _retraso_deteccion_horas(tipo_real, duracion_horas, rng)
        ts_generacion = evento["ts_inicio"] + timedelta(hours=retraso)

        if ts_generacion >= evento["ts_fin"]:
            ts_generacion = evento["ts_fin"] - timedelta(minutes=1)
        if ts_generacion < instalacion:
            ts_generacion = instalacion
        if ts_generacion < periodo_inicio:
            ts_generacion = periodo_inicio
        if ts_generacion >= fin_vigencia:
            continue

        tipo_percibido = evento["id_tipo_evento"]
        if rng.random() < misclassification_rate:
            tipo_percibido = _elegir_distinto(
                ids_tipo, evento["id_tipo_evento"], rng
            )

        prioridad = _prioridad(
            tipo_real, duracion_horas, evento["kwh_desviados"]
        )

        ts_cierre, resultado = _cerrar_alerta(
            ts_generacion,
            periodo_fin_exclusivo,
            prioridad,
            open_probability,
            inconclusive_probability,
            False,
            rng,
        )

        alertas.append(
            (
                id_alerta,
                evento["id_evento"],
                evento["id_medidor"],
                tipo_percibido,
                ts_generacion,
                prioridad,
                ts_cierre,
                resultado,
            )
        )
        id_alerta += 1

    # Falsas alarmas sin evento real asociado.
    # Se genera una Poisson por medidor usando solo sus meses de vigencia.
    for medidor in medidores:
        instalacion = datetime.combine(
            medidor["fecha_instalacion"], time.min
        )
        retiro = (
            datetime.combine(medidor["fecha_retiro"], time.min)
            if medidor["fecha_retiro"] is not None
            else periodo_fin_exclusivo
        )

        vigencia_inicio = max(periodo_inicio, instalacion)
        vigencia_fin_exclusivo = min(periodo_fin_exclusivo, retiro)

        if vigencia_fin_exclusivo <= vigencia_inicio:
            continue

        dias_vigentes = (
            vigencia_fin_exclusivo - vigencia_inicio
        ).total_seconds() / 86400.0
        meses_vigentes = dias_vigentes / 30.0
        cantidad_falsos = _poisson(
            false_positive_rate * meses_vigentes, rng
        )

        for _ in range(cantidad_falsos):
            ts_generacion = _instante_aleatorio(
                vigencia_inicio, vigencia_fin_exclusivo, rng
            )
            if ts_generacion is None:
                continue

            id_tipo_evento = rng.choice(ids_tipo)
            prioridad = rng.choices(
                [2, 3, 4], weights=[0.10, 0.45, 0.45], k=1
            )[0]

            ts_cierre, resultado = _cerrar_alerta(
                ts_generacion,
                periodo_fin_exclusivo,
                prioridad,
                open_probability,
                inconclusive_probability,
                True,
                rng,
            )

            alertas.append(
                (
                    id_alerta,
                    None,
                    medidor["id_medidor"],
                    id_tipo_evento,
                    ts_generacion,
                    prioridad,
                    ts_cierre,
                    resultado,
                )
            )
            id_alerta += 1

    alertas.sort(key=lambda fila: (fila[4], fila[0]))
    return alertas


# ======================================================================
# INSERCION
# ======================================================================


def generar_alertas(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    """Genera e inserta alertas. Devuelve el total insertado."""
    alert_config = _config_alertas(config)
    replace_existing = bool(alert_config.get("replace_existing", False))
    batch_size = int(alert_config.get("batch_size", 5000))

    if batch_size <= 0:
        raise ValueError("alerts.batch_size debe ser mayor que cero")

    existentes = _contar_alertas(connection)
    if existentes and not replace_existing:
        raise RuntimeError(
            f"energia.alerta ya contiene {existentes:,} filas. "
            "Para evitar duplicados, conserva la tabla vacia o configura "
            "alerts.replace_existing: true."
        )

    sql = """
        INSERT INTO energia.alerta (
            id_alerta,
            id_evento,
            id_medidor,
            id_tipo_evento,
            ts_generacion,
            prioridad,
            ts_cierre,
            resultado
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    try:
        if replace_existing and existentes:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM energia.alerta")

        alertas = construir_alertas(connection, config, rules)

        with connection.cursor() as cursor:
            for inicio in range(0, len(alertas), batch_size):
                lote = alertas[inicio:inicio + batch_size]
                cursor.executemany(sql, lote)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    eventos_por_id = {
        evento["id_evento"]: evento for evento in _cargar_eventos(connection)
    }
    asociadas = sum(1 for alerta in alertas if alerta[1] is not None)
    falsas = len(alertas) - asociadas
    abiertas = sum(1 for alerta in alertas if alerta[6] is None)
    mal_clasificadas = sum(
        1
        for alerta in alertas
        if alerta[1] is not None
        and eventos_por_id[alerta[1]]["id_tipo_evento"] != alerta[3]
    )

    print(f"[OK] Alertas generadas: {len(alertas):,}")
    print(f"[OK] Alertas asociadas a eventos: {asociadas:,}")
    print(f"[OK] Falsos positivos: {falsas:,}")
    print(f"[OK] Alertas abiertas: {abiertas:,}")
    print(f"[OK] Clasificaciones incorrectas: {mal_clasificadas:,}")
    print("[OK] Alertas dentro de la vigencia de cada medidor")

    return len(alertas)


# Alias uniforme para main.py.
def generar(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    return generar_alertas(connection, config, rules)
