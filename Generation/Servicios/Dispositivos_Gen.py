"""
    GENERADOR DE MEDIDORES (Generation/Servicios/Dispositivos_Gen.py)

    Genera energia.medidor en proporcion 1:1 con los servicios
    ya insertados en PostgreSQL, mas un numero configurable de
    reemplazos de medidor (feature meter_replacements).

    Reglas (config/rules.yaml -> meters):
      - marcas con pesos (brand_distribution)
      - multiplicador segun rango de carga del servicio
      - calidad de enlace 50-100, castigada en zonas perifericas
      - numero de serie unico de hasta 24 caracteres
"""

import random


# ----------------------------------------------------------------------
# Consultas
# ----------------------------------------------------------------------

def _cargar_servicios_con_zona(connection):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.id_servicio, s.carga_contratada_kw, s.id_zona,
                   z.tipo_urbano
            FROM energia.servicio s
            INNER JOIN energia.zona z ON z.id_zona = s.id_zona
            ORDER BY s.id_servicio
            """
        )
        return [
            {
                "id_servicio": r[0],
                "carga_kw": float(r[1] or 0),
                "id_zona": r[2],
                "tipo_urbano": r[3],
            }
            for r in cur.fetchall()
        ]


# ----------------------------------------------------------------------
# Reglas auxiliares
# ----------------------------------------------------------------------

def _elegir_marca(reglas_meters):
    marcas = reglas_meters["brands"]
    return random.choices(
        list(marcas.keys()), weights=list(marcas.values()), k=1
    )[0]


def _elegir_multiplicador(reglas_meters):
    # Distribucion de multiplicadores definida en rules.yaml
    mults = reglas_meters["multipliers"]
    return random.choices(
        list(mults.keys()), weights=list(mults.values()), k=1
    )[0]


def _numero_serie(marca, secuencial, fecha_ref):
    """Serie unica de maximo 24 caracteres."""
    prefijo = marca[:4]
    anio = str(fecha_ref.year)[-2:]
    base = f"{prefijo}-{anio}{secuencial:08d}"
    digito = sum(ord(c) for c in base) % 10
    return f"{base}-{digito}"  # 4 + 1 + 2 + 8 + 1 + 1 = 17 chars


# ----------------------------------------------------------------------
# Generador principal
# ----------------------------------------------------------------------

def generar_medidores(connection, config, rules, n_reemplazos=None):
    """
    Inserta los medidores activos y devuelve la lista de medidores
    creados (para que Lecturas_Gen los consuma).

    Los reemplazos se insertan tras los activos y producen:
      - UPDATE del medidor original (fecha_retiro)
      - INSERT del medidor nuevo (activo)
    """
    reglas_meters = rules["meters"]
    batch_size = config["performance"]["batch_size"]
    fecha_ini = config["generation"]["date_start"]

    if n_reemplazos is None:
        n_reemplazos = config["generation"].get("replacement_meters", 0)

    servicios = _cargar_servicios_con_zona(connection)
    rango_calidad = reglas_meters["link_quality"]

    medidores_activos = []
    lote = []

    for idx, svc in enumerate(servicios, start=1):
        marca = _elegir_marca(reglas_meters)
        fecha_instalacion = fecha_ini

        # Calidad base, castigada en periferia.
        calidad = random.randint(rango_calidad["min"], rango_calidad["max"])
        if svc["tipo_urbano"] == "PERIFERIA":
            calidad = max(calidad - 6, 50)

        fila = [
            idx,                                  # id_medidor
            svc["id_servicio"],
            _numero_serie(marca, idx, fecha_ini),
            marca,
            _elegir_multiplicador(reglas_meters),
            fecha_instalacion.isoformat(),
            None,                                 # fecha_retiro (activo)
            calidad,
        ]
        medidores_activos.append(fila)
        lote.append(fila)

        if len(lote) >= batch_size:
            yield lote
            lote = []

    if lote:
        yield lote

    # ------------------------------------------------------------------
    # Reemplazos (feature meter_replacements)
    # ------------------------------------------------------------------
    if n_reemplazos > 0 and medidores_activos:
        elegidos = random.sample(medidores_activos, min(n_reemplazos, len(medidores_activos)))
        lote_reemplazos = []
        proximo_id = len(medidores_activos) + 1

        for original in elegidos:
            id_medidor_viejo, id_servicio = original[0], original[1]

            # Fecha de retiro razonable dentro del rango de la corrida.
            dias_offset = random.randint(30, 80)
            fecha_retiro = fecha_ini.toordinal() + dias_offset
            fecha_retiro = fecha_ini.__class__.fromordinal(fecha_retiro)

            # Nuevo medidor (mismo servicio, serie nueva).
            marca = _elegir_marca(reglas_meters)
            nuevo = [
                proximo_id,
                id_servicio,
                _numero_serie(marca, proximo_id, fecha_retiro),
                marca,
                _elegir_multiplicador(reglas_meters),
                fecha_retiro.isoformat(),
                None,
                random.randint(rango_calidad["min"], rango_calidad["max"]),
            ]
            lote_reemplazos.append((id_medidor_viejo, id_servicio, nuevo))
            proximo_id += 1

        # 1) Marcar retirados y 2) insertar nuevos, en un solo paso
        #    por servicio dentro de una transaccion.
        with connection.cursor() as cur:
            for id_viejo, id_servicio, nuevo in lote_reemplazos:
                cur.execute(
                    "UPDATE energia.medidor SET fecha_retiro = %s "
                    "WHERE id_medidor = %s",
                    (nuevo[5], id_viejo),
                )
                cur.execute(
                    """
                    INSERT INTO energia.medidor
                        (id_medidor, id_servicio, numero_serie, marca,
                         multiplicador, fecha_instalacion, fecha_retiro,
                         calidad_enlace)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    tuple(nuevo),
                )
        connection.commit()

        if lote_reemplazos:
            print(
                f"    Medidores: {len(lote_reemplazos)} reemplazos "
                f"aplicados (feature meter_replacements)"
            )

    print(
        f"    Medidores: {len(medidores_activos)} activos "
        f"+ {n_reemplazos if n_reemplazos <= len(medidores_activos) else len(medidores_activos)} "
        f"reemplazos en total"
    )