"""
    GENERADOR DE LECTURAS (Generation/Lecturas_Gen.py)

    Produce energia.lectura + energia.evento + energia.alerta
    en lotes de performance.batch_size (100,000 por defecto).

    Ecuacion del consumo real de cada hora:

        consumo_real = consumo_base (tipo_servicio)
                     x factor_perfil (perfil_carga_horaria: H/S/D)
                     x factor_socioeconomico (zona)
                     x factor_estacional (calendario)
                     x factor_aleatorio (rules.consumption.random_factor)
                     x factor_temperatura (sensibilidad del tipo)
                     [x reduccion solar 9h-17h si tiene_solar]

    Los eventos (rules/calendario y tablas tipo_evento) aplican su
    efecto sobre consumo_kwh (lo que reporta el medidor):

        INCREMENTO / REDUCCION : consumo_kwh = real x intensidad
        CONGELAMIENTO          : consumo_kwh = valor plano
        NULIFICACION           : consumo_kwh = NULL (no reporta)

    Las alertas se generan a partir de los eventos detectados
    (prob_deteccion) mas una proporcion de falsas alarmas.
"""

import random
from datetime import datetime, timedelta

import numpy as np


# ----------------------------------------------------------------------
# Consultas preparatorias
# ----------------------------------------------------------------------

def _cargar_medidores(connection):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id_medidor, id_servicio, multiplicador
            FROM energia.medidor
            WHERE fecha_retiro IS NULL
            ORDER BY id_medidor
            """
        )
        return [{"id": r[0], "id_servicio": r[1], "mult": int(r[2])} for r in cur.fetchall()]


def _cargar_servicios(connection):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.id_servicio, s.id_tipo_servicio, s.id_zona,
                   s.tiene_solar, s.carga_contratada_kw, z.factor_socioeconomico
            FROM energia.servicio s
            INNER JOIN energia.zona z ON z.id_zona = s.id_zona
            """
        )
        return {
            r[0]: {
                "id_tipo_servicio": r[1],
                "id_zona": r[2],
                "solar": r[3],
                "carga_kw": float(r[4]),
                "socio": float(r[5]),
            }
            for r in cur.fetchall()
        }


def _cargar_tipos_servicio(connection):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id_tipo_servicio, consumo_base_kwh_h, sensibilidad_temp, "
            "       factor_dispersion "
            "FROM energia.tipo_servicio"
        )
        return {
            r[0]: {
                "consumo_base": float(r[1]),
                "sensibilidad": float(r[2]),
                "dispersion": float(r[3]),
            }
            for r in cur.fetchall()
        }


def _cargar_perfiles(connection):
    """perfiles[(id_tipo_servicio, tipo_dia)] = [factor x 24 horas]"""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id_tipo_servicio, tipo_dia, hora, factor "
            "FROM energia.perfil_carga_horaria "
            "ORDER BY id_tipo_servicio, tipo_dia, hora"
        )
        perfiles = {}
        for id_tipo, tipo_dia, hora, factor in cur.fetchall():
            perfiles.setdefault((id_tipo, tipo_dia), [0.0] * 24)[hora] = float(factor)
        return perfiles


def _cargar_tipos_evento(connection):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id_tipo_evento, clave, efecto, duracion_min_h, "
            "       duracion_max_h, intensidad_min, intensidad_max, "
            "       tasa_por_medidor_mes, prob_deteccion "
            "FROM energia.tipo_evento "
            "WHERE tasa_por_medidor_mes > 0"
        )
        return [
            {
                "id": r[0],
                "clave": r[1],
                "efecto": r[2],
                "dur_min": int(r[3]),
                "dur_max": int(r[4]),
                "int_min": float(r[5]) if r[5] is not None else None,
                "int_max": float(r[6]) if r[6] is not None else None,
                "tasa_mes": float(r[7]),
                "prob_det": float(r[8]),
            }
            for r in cur.fetchall()
        ]


def _cargar_calendario_desde_bd(connection, fecha_desde, fecha_hasta):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT fecha, tipo_dia, factor_estacional,
                   temp_min_c, temp_max_c
            FROM energia.calendario
            WHERE fecha BETWEEN %s AND %s
            ORDER BY fecha
            """,
            (fecha_desde, fecha_hasta),
        )
        return [
            {
                "fecha": r[0],
                "tipo_dia": r[1],
                "factor_estacional": float(r[2]),
                "temp_media": (float(r[3]) + float(r[4])) / 2.0,
            }
            for r in cur.fetchall()
        ]


# ----------------------------------------------------------------------
# Generacion de eventos
# ----------------------------------------------------------------------

def _generar_eventos(medidores, tipos_evento, config, rng):
    """
    Genera los eventos sinteticos de energia.evento.

    En 90 dias hay 3 meses, por lo que la probabilidad de que un
    medidor padezca el evento durante la corrida es:
        p = min(tasa_por_medidor_mes * 3, 1)
    """
    fecha_desde = config["generation"]["date_start"]
    fecha_hasta = config["generation"]["date_end"]
    total_dias = (fecha_hasta - fecha_desde).days + 1

    eventos = []
    id_evento = 1

    for medidor in medidores:
        for te in tipos_evento:
            prob = min(te["tasa_mes"] * 3.0, 1.0)
            if rng.random() >= prob:
                continue

            dia = rng.randint(0, total_dias - 1)
            ts_inicio = datetime.combine(
                fecha_desde, datetime.min.time()
            ) + timedelta(days=dia, hours=rng.randint(0, 23))

            dur_h = rng.randint(te["dur_min"], te["dur_max"])
            ts_fin = ts_inicio + timedelta(hours=dur_h)

            if te["int_min"] is not None:
                intensidad = round(rng.uniform(te["int_min"], te["int_max"]), 3)
            else:
                intensidad = None

            eventos.append(
                {
                    "id_evento": id_evento,
                    "id_medidor": medidor["id"],
                    "id_tipo_evento": te["id"],
                    "efecto": te["efecto"],
                    "ts_inicio": ts_inicio,
                    "ts_fin": ts_fin,
                    "intensidad": intensidad,
                    "prob_det": te["prob_det"],
                }
            )
            id_evento += 1

    return eventos


# ----------------------------------------------------------------------
# Generador de lecturas (el corazon del proyecto)
# ----------------------------------------------------------------------

def generar_lecturas(connection, config, rules, calendario, limitar_medidores=None):
    """
    Genera eventos, lecturas y alertas.

    - eventos: se insertan primero en energia.evento (con kwh_desviados
      en 0 y se actualizan al final).
    - lecturas: se producen por lotes de performance.batch_size y cada
      lote se envia con COPY.
    - alertas: por evento detectado + falsas alarmas.

    `limitar_medidores` sirve para corridas demo (p.ej. 60 medidores
    garantizan >100,000 lecturas en 90 dias: 60 x 2160 = 129,600).
    """
    batch_size = config["performance"]["batch_size"]
    features = config["features"]
    fecha_desde = config["generation"]["date_start"]
    fecha_hasta = config["generation"]["date_end"]

    rng = random.Random(config["generation"]["seed"])

    # --- Carga de contexto ---
    medidores = _cargar_medidores(connection)
    if limitar_medidores:
        medidores = medidores[:limitar_medidores]
    servicios = _cargar_servicios(connection)
    tipos = _cargar_tipos_servicio(connection)
    perfiles = _cargar_perfiles(connection)
    tipos_evento = _cargar_tipos_evento(connection)

    reglas_consumo = rules["consumption"]
    reglas_solar = rules["solar"]

    # --- Eventos ---
    eventos = []
    if features.get("events", True):
        eventos = _generar_eventos(medidores, tipos_evento, config, rng)
        _insertar_eventos(connection, eventos)

    eventos_por_medidor = {}
    for ev in eventos:
        eventos_por_medidor.setdefault(ev["id_medidor"], []).append(ev)

    # --- Precomputo global por dia del calendario ---
    # timestamps planos (dias x 24), indices, estacional, temp, tipo_dia
    ndias = len(calendario)
    n_slots = ndias * 24
    ts_flat = []
    idx_tipo_dia = []
    estacional_arr = np.ones(ndias, dtype=np.float64)
    temp_arr = np.ones(ndias, dtype=np.float64)
    clave_idx = {"D": 0, "S": 1, "H": 2}
    for i, dia in enumerate(calendario):
        base_ts = datetime.combine(dia["fecha"], datetime.min.time())
        for hora in range(24):
            ts_flat.append((base_ts + timedelta(hours=hora)).isoformat())
        idx_tipo_dia.append(clave_idx.get(dia["tipo_dia"], 0))
        estacional_arr[i] = dia["factor_estacional"]
        temp_arr[i] = dia["temp_media"]
    idx_tipo_dia = np.array(idx_tipo_dia, dtype=np.int64)      # (ndias,)

    # Stack de perfiles por tipo_servicio: filas (D, S, H)
    perfil_np = {
        clave: np.array(vals, dtype=np.float64)
        for clave, vals in perfiles.items()
    }
    perfil_stack = {}
    for id_tipo in tipos:
        perfil_stack[id_tipo] = np.stack(
            [
                perfil_np.get((id_tipo, "D"), np.ones(24)),
                perfil_np.get((id_tipo, "S"), np.ones(24)),
                perfil_np.get((id_tipo, "H"), np.ones(24)),
            ]
        )  # (3, 24)

    if features.get("solar", True):
        horas_solares = np.zeros(24)
        horas_solares[
            reglas_solar["start_hour"]: reglas_solar["end_hour"] + 1
        ] = 1.0
    else:
        horas_solares = None

    intervalo = config["generation"]["interval_minutes"]
    lecturas_totales = 0
    lote = []
    desvios_por_evento = {}
    seed_base = int(config["generation"]["seed"])

    for med in medidores:
        svc = servicios[med["id_servicio"]]
        tipo = tipos[svc["id_tipo_servicio"]]
        socio = svc["socio"]

        # RNG numpy derivado por medidor (reproducible y rapido)
        rng_m = np.random.default_rng(
            (seed_base * 2654435761 + med["id"] * 40503) % (2**32)
        )

        # Matriz de consumo real (ndias, 24) en una sola pasada
        perfil_mat = perfil_stack[svc["id_tipo_servicio"]][idx_tipo_dia]
        f_min = reglas_consumo["random_factor"]["min"]
        f_max = reglas_consumo["random_factor"]["max"]
        aleatorio = (
            rng_m.random((ndias, 24)) * (f_max - f_min) + f_min
        )

        matriz = (
            tipo["consumo_base"]
            * perfil_mat
            * socio
            * estacional_arr.reshape(-1, 1)
            * aleatorio
        )
        if reglas_consumo.get("use_temperature_factor"):
            matriz = matriz * (
                1.0
                + tipo["sensibilidad"]
                * ((temp_arr - 15.0) / 10.0).reshape(-1, 1)
            )
        if horas_solares is not None and svc["solar"]:
            reduccion = rng_m.uniform(
                reglas_solar["reduction"]["min"],
                reglas_solar["reduction"]["max"],
            )
            matriz = matriz * (1.0 - horas_solares * reduccion)

        # Plano: consumo real y kWh (aplicar eventos con mascaras)
        flat_real = matriz.ravel()                      # (n_slots,)
        flat_kwh = flat_real.copy()
        ev_flat = np.full(n_slots, -1, dtype=np.int64)

        for ev in eventos_por_medidor.get(med["id"], []):
            d0 = (ev["ts_inicio"].date() - fecha_desde).days
            h0 = ev["ts_inicio"].hour
            d1 = (ev["ts_fin"].date() - fecha_desde).days
            h1 = ev["ts_fin"].hour
            i0 = max(0, d0 * 24 + h0)
            i1 = min(n_slots - 1, d1 * 24 + h1)
            idx = np.arange(i0, i1 + 1)

            ev_flat[idx] = ev["id_evento"]
            if ev["efecto"] == "NULIFICACION":
                flat_kwh[idx] = np.nan
                desvios = np.nansum(
                    np.abs(flat_kwh[idx] - flat_real[idx])
                )
            elif ev["efecto"] in ("INCREMENTO", "REDUCCION"):
                flat_kwh[idx] = flat_real[idx] * ev["intensidad"]
                desvios = np.sum(
                    np.abs(flat_kwh[idx] - flat_real[idx])
                )
            else:  # CONGELAMIENTO / plano: consumido == real
                desvios = 0.0
            desvios_por_evento[ev["id_evento"]] = (
                desvios_por_evento.get(ev["id_evento"], 0.0) + float(desvios)
            )

        # Construccion plana de filas del lote
        real_list = np.round(flat_real, 4).tolist()
        kwh_list = np.round(flat_kwh, 4).tolist()
        ev_list = ev_flat.tolist()
        id_med = med["id"]
        lote.extend(
            (
                id_med,
                ts_flat[i],
                None if kwh_list[i] != kwh_list[i] else kwh_list[i],
                real_list[i],
                None if ev_list[i] < 0 else ev_list[i],
            )
            for i in range(n_slots)
        )

        if len(lote) >= batch_size:
            _copiar_lote(connection, lote, batch_size, lecturas_totales)
            lecturas_totales += len(lote)
            lote = []

        # Nota de progreso cada 500 medidores
        if med["id"] % 500 == 0:
            print(f"    Lecturas: {med['id']}/{len(medidores)} medidores procesados")

    if lote:
        _copiar_lote(connection, lote, batch_size, lecturas_totales)
        lecturas_totales += len(lote)

    # --- kwh_desviados por evento ---
    if eventos:
        with connection.cursor() as cur:
            for id_evento, desvios in desvios_por_evento.items():
                cur.execute(
                    "UPDATE energia.evento SET kwh_desviados = %s "
                    "WHERE id_evento = %s",
                    (round(desvios, 4), id_evento),
                )
        connection.commit()

    # --- Alertas ---
    alertas = 0
    if features.get("alerts", True) and features.get("events", True):
        alertas = _generar_alertas(connection, eventos, medidores, rng)

    return lecturas_totales, len(eventos), alertas


def _insertar_eventos(connection, eventos):
    from database.insertar import copy_lote

    filas = [
        [
            ev["id_evento"],
            ev["id_medidor"],
            ev["id_tipo_evento"],
            ev["ts_inicio"].isoformat(),
            ev["ts_fin"].isoformat(),
            ev["intensidad"],
            0,  # kwh_desviados inicial
        ]
        for ev in eventos
    ]
    if filas:
        copy_lote(
            connection,
            "evento",
            [
                "id_evento",
                "id_medidor",
                "id_tipo_evento",
                "ts_inicio",
                "ts_fin",
                "intensidad",
                "kwh_desviados",
            ],
            filas,
            etiqueta="Eventos",
        )
        connection.commit()


def _copiar_lote(connection, lote, batch_size, acumulado):
    from database.insertar import copy_lote

    copy_lote(
        connection,
        "lectura",
        ["id_medidor", "ts", "consumo_kwh", "consumo_real_kwh", "id_evento"],
        lote,
        etiqueta="Lecturas",
    )
    connection.commit()


def _generar_alertas(connection, eventos, medidores, rng):
    """Abre alertas para eventos detectados + falsas alarmas."""
    from database.insertar import copy_lote

    # Prioridad por efecto (1 = mas critico)
    prioridad_efecto = {
        "NULIFICACION": 1,
        "INCREMENTO": 1,
        "REDUCCION": 2,
        "CONGELAMIENTO": 3,
    }

    filas = []
    id_alerta = 1

    for ev in eventos:
        if rng.random() > ev["prob_det"]:
            continue
        prioridad = prioridad_efecto.get(ev["efecto"], 2)
        filas.append(
            [
                id_alerta,
                ev["id_evento"],
                ev["id_medidor"],
                ev["id_tipo_evento"],
                ev["ts_inicio"].isoformat(),
                prioridad,
                None,
                None,
            ]
        )
        id_alerta += 1

    # Falsas alarmas (5% adicional, sin evento asociado)
    n_falsas = max(1, int(len(filas) * 0.05))
    fecha_desde = None
    fecha_hasta = None
    # Rango de tiempo de los eventos generados
    ts_eventos = [e["ts_inicio"] for e in eventos]
    if ts_eventos:
        fecha_desde = min(ts_eventos)
        fecha_hasta = max(e["ts_fin"] for e in eventos)

    for _ in range(n_falsas):
        med = rng.choice(medidores)
        if fecha_desde is None:
            fecha_desde = datetime(2026, 1, 1)
            fecha_hasta = datetime(2026, 3, 31)
        ts_falsa = fecha_desde + timedelta(
            seconds=rng.randint(
                0,
                max(1, int((fecha_hasta - fecha_desde).total_seconds())),
            )
        )
        filas.append(
            [
                id_alerta,
                None,
                med["id"],
                1,  # tipo_evento 1 (JAMAS_ANOMALIA del catalogo)
                ts_falsa.isoformat(),
                4,
                None,
                None,
            ]
        )
        id_alerta += 1

    if filas:
        copy_lote(
            connection,
            "alerta",
            [
                "id_alerta",
                "id_evento",
                "id_medidor",
                "id_tipo_evento",
                "ts_generacion",
                "prioridad",
                "ts_cierre",
                "resultado",
            ],
            filas,
            etiqueta="Alertas",
        )
        connection.commit()

    return len(filas)