"""
    GENERADOR DE SERVICIOS (Generation/Servicios_Gen.py)

    Lee los catalogos desde PostgreSQL (zona, tipo_servicio, tarifa)
    y produce los registros de energia.servicio por lotes.

    El lote se define en config/generation.yaml (performance.batch_size)
    y se envia a PostgreSQL con COPY desde database/insertar.py.

    Reglas aplicadas (config/rules.yaml -> services):
      - distribucion por categoria (category_distribution)
      - zonas ponderadas por viviendas habitadas (use_housing_weights)
      - carga contratada y probabilidad solar por categoria
"""

import random


# ----------------------------------------------------------------------
# Consultas de catalogos
# ----------------------------------------------------------------------

def _cargar_zonas(connection):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id_zona, nombre, tipo_urbano, factor_socioeconomico, "
            "       viviendas_habitadas "
            "FROM energia.zona ORDER BY id_zona"
        )
        return [
            {
                "id_zona": r[0],
                "nombre": r[1],
                "tipo_urbano": r[2],
                "factor_socioeconomico": float(r[3]),
                "viviendas": r[4] or 100,
            }
            for r in cur.fetchall()
        ]


def _cargar_tipos(connection):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id_tipo_servicio, clave, nombre, categoria, "
            "       consumo_base_kwh_h "
            "FROM energia.tipo_servicio ORDER BY id_tipo_servicio"
        )
        return [
            {
                "id": r[0],
                "clave": r[1],
                "nombre": r[2],
                "categoria": r[3],
                "consumo_base": float(r[4]),
            }
            for r in cur.fetchall()
        ]


def _cargar_tarifas(connection):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id_tarifa, codigo, categoria "
            "FROM energia.tarifa ORDER BY id_tarifa"
        )
        return [
            {"id": r[0], "codigo": r[1], "categoria": r[2]}
            for r in cur.fetchall()
        ]


# ----------------------------------------------------------------------
# Reglas auxiliares
# ----------------------------------------------------------------------

# Tarifas candidatas por categoria de tipo de servicio.
TARIFA_POR_CATEGORIA = {
    "RESIDENCIAL": ["1", "1C", "DAC"],
    "COMERCIAL": ["PDBT", "GDBT"],
    "PUBLICO": ["PDBT", "GDMTH"],
    "SERVICIO": ["GDMTH"],
    "ALUMBRADO": ["APBT"],
    "MOVILIDAD": ["PDBT"],
}


def _elegir_tarifa(tarifas_por_codigo, categoria, carga_kw):
    codigos = TARIFA_POR_CATEGORIA.get(categoria, ["PDBT"])
    # Servicios de consumo alto suben de tarifa.
    if carga_kw > 25 and "GDBT" in codigos:
        codigos = ["GDBT"]
    if carga_kw > 8 and "DAC" in codigos:
        codigos = ["DAC"]
    codigo = random.choice(codigos)
    return tarifas_por_codigo[codigo]["id"]


def _generar_coordenada(rules, zona):
    geo = rules["services"]["geographic_location"]
    lat = random.uniform(geo["latitude"]["min"], geo["latitude"]["max"])
    lon = random.uniform(geo["longitude"]["min"], geo["longitude"]["max"])
    decimales = geo["decimal_places"]
    return round(lat, decimales), round(lon, decimales)


# ----------------------------------------------------------------------
# Generador principal (por lotes)
# ----------------------------------------------------------------------

def generar_servicios(connection, config, rules, n_servicios=None):
    """
    Generador que produce filas de energia.servicio en lotes.

    Devuelve (yield) listas de hasta batch_size filas.
    """

    batch_size = config["performance"]["batch_size"]
    reglas_servicios = rules["services"]

    if n_servicios is None:
        n_servicios = config["generation"]["services"]

    # Distribucion por categoria
    distribucion = reglas_servicios["category_distribution"]
    categorias = list(distribucion.keys())
    pesos = list(distribucion.values())

    # Zonas ponderadas por viviendas
    zonas = _cargar_zonas(connection)
    pesos_zonas = [z["viviendas"] for z in zonas]

    tipos = _cargar_tipos(connection)
    tipos_por_categoria = {}
    for t in tipos:
        tipos_por_categoria.setdefault(t["categoria"], []).append(t)

    tarifas = _cargar_tarifas(connection)
    tarifas_por_codigo = {t["codigo"]: t for t in tarifas}

    ocupacion = reglas_servicios["residential_occupancy"]
    cargas = reglas_servicios["contracted_load_kw"]
    solar_prob = reglas_servicios["solar_probability"]

    lote = []

    for i in range(1, n_servicios + 1):
        # Categoria segun padron
        categoria = random.choices(categorias, weights=pesos, k=1)[0]

        # Zona ponderada por viviendas habitadas
        zona = random.choices(zonas, weights=pesos_zonas, k=1)[0]

        # Tipo de servicio dentro de la categoria
        tipo = random.choice(tipos_por_categoria[categoria])

        # Carga contratada y solar
        rango_carga = cargas[categoria]
        carga_kw = round(random.uniform(rango_carga["min"], rango_carga["max"]), 2)
        tiene_solar = random.random() < solar_prob[categoria]

        # Tarifa compatible
        id_tarifa = _elegir_tarifa(tarifas_por_codigo, categoria, carga_kw)

        # Ocupacion estimada
        if categoria == "RESIDENCIAL":
            ocupacion_estimada = random.randint(ocupacion["min"], ocupacion["max"])
        else:
            ocupacion_estimada = None

        # Ubicacion
        latitud, longitud = _generar_coordenada(rules, zona)

        fila = [
            i,                                                # id_servicio
            f"{i:012d}",                                      # rpu (12 digitos)
            zona["id_zona"],
            tipo["id"],
            id_tarifa,
            f"{tipo['clave']}-{i:06d}",                       # nombre (unico por zona)
            latitud,
            longitud,
            ocupacion_estimada,
            carga_kw,
            tiene_solar,
        ]

        lote.append(fila)

        if len(lote) >= batch_size:
            yield lote
            lote = []

    if lote:
        yield lote