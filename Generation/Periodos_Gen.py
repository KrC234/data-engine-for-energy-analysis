"""
    GENERADOR DE PERIODOS DE FACTURACION (Generation/Periodos_Gen.py)

    Construye energia.periodo_facturacion a partir de las lecturas
    ya insertadas.

    Para cada servicio y mes del rango:
      - consumo_real_kwh = SUM(consumo_real_kwh) del mes
      - registro_inicial / registro_final = acumulado historico
      - clasificacion_dac segun limite de su tarifa
      - folio unico de factura

    Volumen esperado (config completa): 5,000 servicios x 3 meses
    = 15,000 periodos.
"""


def generar_periodos(connection, config):
    """
    Genera e inserta los periodos de facturacion por servicio y mes.
    Devuelve el numero de periodos creados.
    """
    from database.insertar import copy_lote

    features = config["features"]
    if not features.get("billing", True):
        return 0, 0

    # Consumo real por (servicio, mes) desde las lecturas
    query = """
        SELECT m.id_servicio,
               date_trunc('month', l.ts)::date AS mes,
               SUM(l.consumo_real_kwh)         AS consumo_mes
        FROM energia.lectura l
        INNER JOIN energia.medidor m ON m.id_medidor = l.id_medidor
        GROUP BY m.id_servicio, date_trunc('month', l.ts)::date
        ORDER BY m.id_servicio, mes
    """
    with connection.cursor() as cur:
        cur.execute(query)
        filas = cur.fetchall()

    # Limite DAC (sobre el cual la tarifa cambia a DAC)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id_tarifa, COALESCE(limite_dac_kwh_mes, 4000) "
            "FROM energia.tarifa"
        )
        limite_dac = {r[0]: int(r[1]) for r in cur.fetchall()}

    periodo_filas = []
    id_periodo = 1
    acumulado_servicio = {}
    fechas_por_mes = {}

    for id_servicio, mes, consumo_mes in filas:
        consumo_mes = float(consumo_mes or 0.0)
        acumulado_previo = acumulado_servicio.get(id_servicio, 0.0)

        fecha_inicio = mes
        fecha_fin = _fin_de_mes(mes)
        if fechas_por_mes.get(id_servicio) == mes:
            continue
        fechas_por_mes[id_servicio] = mes

        # Folio unico: PF-<servicio>-<mes>
        folio = f"PF-{id_servicio:06d}-{mes.strftime('%Y%m')}"

        # Tarifa del servicio
        with connection.cursor() as cur:
            cur.execute(
                "SELECT id_tarifa FROM energia.servicio WHERE id_servicio = %s",
                (id_servicio,),
            )
            tarifa = cur.fetchone()
            id_tarifa = tarifa[0] if tarifa else 1

        registro_final = acumulado_previo + consumo_mes
        clasificacion_dac = consumo_mes > limite_dac.get(id_tarifa, 4000)

        periodo_filas.append(
            [
                id_periodo,
                id_servicio,
                folio,
                fecha_inicio.isoformat(),
                fecha_fin.isoformat(),
                id_tarifa,
                round(acumulado_previo, 3),
                round(registro_final, 3),
                round(consumo_mes, 3),
                clasificacion_dac,
            ]
        )
        acumulado_servicio[id_servicio] = registro_final
        id_periodo += 1

    if periodo_filas:
        copy_lote(
            connection,
            "periodo_facturacion",
            [
                "id_periodo",
                "id_servicio",
                "folio",
                "fecha_inicio",
                "fecha_fin",
                "id_tarifa_aplicada",
                "registro_inicial_kwh",
                "registro_final_kwh",
                "consumo_real_kwh",
                "clasificacion_dac",
            ],
            periodo_filas,
            etiqueta="Periodos",
        )
        connection.commit()

    return len(periodo_filas)


def _fin_de_mes(mes):
    """Devuelve el ultimo dia del mes dado."""
    if mes.month == 12:
        import datetime as _dt
        return _dt.date(mes.year, 12, 31)
    import calendar as _cal
    ultimo_dia = _cal.monthrange(mes.year, mes.month)[1]
    import datetime as _dt
    return _dt.date(mes.year, mes.month, ultimo_dia)