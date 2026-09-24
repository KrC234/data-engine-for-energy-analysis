"""Generador de servicios sintéticos de HyperDataSynthetic.

Este módulo reemplaza la versión antigua basada en JSON y CSV.

Fuentes utilizadas:
- PostgreSQL: energia.zona, energia.tipo_servicio y energia.tarifa.
- generation.yaml: cantidad de servicios y semilla.
- rules.yaml: distribución, ocupación, carga, solar y coordenadas.

No ejecuta código al importarse y no modifica la estructura de la base.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Any


# ======================================================================
# CONFIGURACION
# ======================================================================


def _seccion_generacion(config: dict[str, Any]) -> dict[str, Any]:
    """Acepta parámetros en la raíz o dentro de generation."""
    generation = config.get("generation")
    return generation if isinstance(generation, dict) else config


def _config_servicios(rules: dict[str, Any]) -> dict[str, Any]:
    section = rules.get("services", {})
    if not isinstance(section, dict):
        raise ValueError("rules.yaml: services debe ser un objeto YAML")
    return section


def _obtener_total_servicios(generation: dict[str, Any]) -> int:
    posibles = (
        "services",
        "number_of_services",
        "numero_servicios",
        "total_servicios",
    )

    for nombre in posibles:
        if nombre in generation:
            total = int(generation[nombre])
            if total <= 0:
                raise ValueError("El número de servicios debe ser mayor que cero")
            return total

    raise KeyError(
        "No se encontró la cantidad de servicios en generation.yaml. "
        "Usa services: 5000"
    )


def _validar_distribucion(distribucion: dict[str, Any]) -> dict[str, float]:
    if not distribucion:
        raise ValueError(
            "rules.yaml no contiene services.category_distribution"
        )

    normalizada = {
        str(categoria).strip().upper(): float(peso)
        for categoria, peso in distribucion.items()
    }

    if any(peso < 0 for peso in normalizada.values()):
        raise ValueError("Los pesos de category_distribution no pueden ser negativos")

    suma = sum(normalizada.values())
    if abs(suma - 1.0) > 0.0001:
        raise ValueError(
            "La suma de services.category_distribution debe ser 1.0. "
            f"Suma actual: {suma:.6f}"
        )

    return normalizada


# ======================================================================
# CONSULTAS A POSTGRESQL
# ======================================================================


def _cargar_zonas(connection: Any) -> list[dict[str, Any]]:
    sql = """
        SELECT
            id_zona,
            nombre,
            tipo_urbano,
            superficie_km2,
            factor_socioeconomico
        FROM energia.zona
        ORDER BY id_zona
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    if not filas:
        raise RuntimeError(
            "energia.zona está vacía. Ejecuta database/sql/02_catalogos.sql primero."
        )

    return [
        {
            "id_zona": int(fila[0]),
            "nombre": fila[1],
            "tipo_urbano": str(fila[2]).upper(),
            "superficie_km2": float(fila[3]),
            "factor_socioeconomico": float(fila[4]),
        }
        for fila in filas
    ]


def _cargar_tipos_servicio(connection: Any) -> list[dict[str, Any]]:
    sql = """
        SELECT
            id_tipo_servicio,
            clave,
            nombre,
            categoria
        FROM energia.tipo_servicio
        ORDER BY id_tipo_servicio
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    if not filas:
        raise RuntimeError(
            "energia.tipo_servicio está vacía. "
            "Ejecuta database/sql/02_catalogos.sql primero."
        )

    return [
        {
            "id_tipo_servicio": int(fila[0]),
            "clave": fila[1],
            "nombre": fila[2],
            "categoria": str(fila[3]).upper(),
        }
        for fila in filas
    ]


def _cargar_tarifas(connection: Any) -> list[dict[str, Any]]:
    sql = """
        SELECT
            id_tarifa,
            codigo,
            nombre,
            categoria
        FROM energia.tarifa
        ORDER BY id_tarifa
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    if not filas:
        raise RuntimeError(
            "energia.tarifa está vacía. Ejecuta database/sql/02_catalogos.sql primero."
        )

    return [
        {
            "id_tarifa": int(fila[0]),
            "codigo": str(fila[1]).upper(),
            "nombre": fila[2],
            "categoria": str(fila[3]).upper(),
        }
        for fila in filas
    ]


def _contar_servicios(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM energia.servicio")
        return int(cursor.fetchone()[0])


def _siguiente_id(connection: Any) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(MAX(id_servicio), 0) + 1 FROM energia.servicio"
        )
        return int(cursor.fetchone()[0])


# ======================================================================
# REGLAS DE ASIGNACION
# ======================================================================


def _categoria_tarifaria(categoria_servicio: str) -> str:
    """Traduce las seis categorías de servicio a las cuatro tarifarias."""
    mapa = {
        "RESIDENCIAL": "DOMESTICA",
        "COMERCIAL": "COMERCIAL",
        "PUBLICO": "SERVICIO_PUBLICO",
        "SERVICIO": "SERVICIO_PUBLICO",
        "ALUMBRADO": "ALUMBRADO",
        "MOVILIDAD": "SERVICIO_PUBLICO",
    }

    try:
        return mapa[categoria_servicio]
    except KeyError as error:
        raise ValueError(
            f"No existe mapeo tarifario para {categoria_servicio!r}"
        ) from error


def _tarifas_compatibles(
    tarifas: list[dict[str, Any]],
    categoria_servicio: str,
) -> list[dict[str, Any]]:
    categoria = _categoria_tarifaria(categoria_servicio)
    candidatas = [t for t in tarifas if t["categoria"] == categoria]

    # Un servicio residencial nuevo no comienza en DAC. Esa tarifa se reserva
    # para la reclasificación posterior de Facturacion_Gen.py.
    if categoria_servicio == "RESIDENCIAL":
        no_dac = [t for t in candidatas if t["codigo"] != "DAC"]
        if no_dac:
            candidatas = no_dac

    if not candidatas:
        raise RuntimeError(
            f"No hay tarifas compatibles con la categoría {categoria_servicio}"
        )

    return candidatas


def _elegir_zona(
    zonas: list[dict[str, Any]],
    usar_pesos: bool,
    rng: random.Random,
) -> dict[str, Any]:
    """Selecciona una zona.

    La tabla actual no tiene una columna de viviendas habitadas. Mientras esa
    columna no exista, superficie_km2 sirve como un peso territorial estable.
    Si use_housing_weights es false, la selección es uniforme.
    """
    if not usar_pesos:
        return rng.choice(zonas)

    pesos = [max(zona["superficie_km2"], 0.001) for zona in zonas]
    return rng.choices(zonas, weights=pesos, k=1)[0]


def _generar_rpu(id_servicio: int, rng: random.Random) -> str:
    """Genera una clave única de exactamente 12 dígitos."""
    prefijo = rng.randint(10, 99)
    cuerpo = id_servicio % 1_000_000_000
    base = f"{prefijo:02d}{cuerpo:09d}"
    digito = sum(int(caracter) for caracter in base) % 10
    return f"{base}{digito}"


def _generar_nombre(
    id_servicio: int,
    zona: dict[str, Any],
    tipo: dict[str, Any],
    rng: random.Random,
) -> str:
    calles = (
        "Av. del Valle",
        "Calle del Bosque",
        "Privada del Sol",
        "Paseo de la Energia",
        "Circuito del Nevado",
        "Camino de los Pinos",
        "Calle de la Luz",
        "Andador Central",
    )
    numero = rng.randint(1, 2999)
    calle = rng.choice(calles)
    return f"{tipo['clave']} | {calle} {numero} | {zona['nombre']} | S-{id_servicio:05d}"


def _generar_coordenadas(
    services_rules: dict[str, Any],
    id_zona: int,
    cantidad_zonas: int,
    rng: random.Random,
) -> tuple[float, float]:
    geo = services_rules.get("geographic_location", {})

    if not geo.get("enabled", True):
        raise ValueError(
            "geographic_location debe estar habilitado porque latitud y "
            "longitud son NOT NULL en energia.servicio"
        )

    lat_rules = geo.get("latitude", {})
    lon_rules = geo.get("longitude", {})

    lat_min = float(lat_rules.get("min", 19.180000))
    lat_max = float(lat_rules.get("max", 19.420000))
    lon_min = float(lon_rules.get("min", -99.780000))
    lon_max = float(lon_rules.get("max", -99.550000))
    decimales = int(geo.get("decimal_places", 6))

    if lat_min >= lat_max or lon_min >= lon_max:
        raise ValueError("Los rangos de latitud o longitud son inválidos")

    # Distribuye centros sintéticos de zona dentro del rectángulo y añade
    # una dispersión pequeña. No pretende reproducir coordenadas reales.
    posicion = (id_zona - 1) / max(cantidad_zonas - 1, 1)
    centro_lat = lat_min + (lat_max - lat_min) * posicion
    centro_lon = lon_max - (lon_max - lon_min) * posicion

    dispersion_lat = (lat_max - lat_min) / max(cantidad_zonas, 1)
    dispersion_lon = (lon_max - lon_min) / max(cantidad_zonas, 1)

    latitud = rng.uniform(
        max(lat_min, centro_lat - dispersion_lat),
        min(lat_max, centro_lat + dispersion_lat),
    )
    longitud = rng.uniform(
        max(lon_min, centro_lon - dispersion_lon),
        min(lon_max, centro_lon + dispersion_lon),
    )

    return round(latitud, decimales), round(longitud, decimales)


def _generar_ocupacion(
    categoria: str,
    services_rules: dict[str, Any],
    rng: random.Random,
) -> int | None:
    if categoria != "RESIDENCIAL":
        return None

    reglas = services_rules.get("residential_occupancy", {})
    minimo = int(reglas.get("min", 1))
    maximo = int(reglas.get("max", 7))

    if minimo < 1 or maximo < minimo:
        raise ValueError("Rango residential_occupancy inválido")

    return rng.randint(minimo, maximo)


def _generar_carga(
    categoria: str,
    services_rules: dict[str, Any],
    rng: random.Random,
) -> float:
    reglas = services_rules.get("contracted_load_kw", {})

    if categoria not in reglas:
        raise KeyError(
            f"Falta services.contracted_load_kw.{categoria} en rules.yaml"
        )

    minimo = float(reglas[categoria]["min"])
    maximo = float(reglas[categoria]["max"])

    if minimo <= 0 or maximo < minimo:
        raise ValueError(f"Rango de carga inválido para {categoria}")

    return round(rng.uniform(minimo, maximo), 2)


def _generar_solar(
    categoria: str,
    services_rules: dict[str, Any],
    rng: random.Random,
) -> bool:
    probabilidades = services_rules.get("solar_probability", {})
    probabilidad = float(probabilidades.get(categoria, 0.0))

    if not 0 <= probabilidad <= 1:
        raise ValueError(
            f"Probabilidad solar inválida para {categoria}: {probabilidad}"
        )

    return rng.random() < probabilidad


# ======================================================================
# CONSTRUCCION E INSERCION
# ======================================================================


def construir_servicios(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> list[tuple[Any, ...]]:
    generation = _seccion_generacion(config)
    services_rules = _config_servicios(rules)

    total = _obtener_total_servicios(generation)
    semilla = int(generation.get("seed", generation.get("semilla", 42)))
    rng = random.Random(semilla + 1000)

    distribucion = _validar_distribucion(
        services_rules.get("category_distribution", {})
    )

    zonas = _cargar_zonas(connection)
    tipos = _cargar_tipos_servicio(connection)
    tarifas = _cargar_tarifas(connection)
    siguiente_id = _siguiente_id(connection)

    tipos_por_categoria: dict[str, list[dict[str, Any]]] = {}
    for categoria in distribucion:
        candidatos = [t for t in tipos if t["categoria"] == categoria]
        if not candidatos:
            raise RuntimeError(
                f"No hay tipos de servicio para la categoría {categoria}"
            )
        tipos_por_categoria[categoria] = candidatos

    categorias = list(distribucion.keys())
    pesos = list(distribucion.values())
    categorias_asignadas = rng.choices(categorias, weights=pesos, k=total)
    usar_pesos = bool(services_rules.get("use_housing_weights", True))

    filas = []

    for desplazamiento, categoria in enumerate(categorias_asignadas):
        id_servicio = siguiente_id + desplazamiento
        zona = _elegir_zona(zonas, usar_pesos, rng)
        tipo = rng.choice(tipos_por_categoria[categoria])
        tarifa = rng.choice(_tarifas_compatibles(tarifas, categoria))

        latitud, longitud = _generar_coordenadas(
            services_rules,
            zona["id_zona"],
            len(zonas),
            rng,
        )

        filas.append(
            (
                id_servicio,
                _generar_rpu(id_servicio, rng),
                zona["id_zona"],
                tipo["id_tipo_servicio"],
                tarifa["id_tarifa"],
                _generar_nombre(id_servicio, zona, tipo, rng),
                latitud,
                longitud,
                _generar_ocupacion(categoria, services_rules, rng),
                _generar_carga(categoria, services_rules, rng),
                _generar_solar(categoria, services_rules, rng),
            )
        )

    return filas


def generar_servicios(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    """Genera e inserta servicios en energia.servicio."""
    generation = _seccion_generacion(config)
    section = generation.get("service_generation", {})
    section = section if isinstance(section, dict) else {}

    replace_existing = bool(section.get("replace_existing", False))
    batch_size = int(section.get("batch_size", 1000))

    if batch_size <= 0:
        raise ValueError("service_generation.batch_size debe ser mayor que cero")

    existentes = _contar_servicios(connection)

    if existentes and not replace_existing:
        raise RuntimeError(
            f"energia.servicio ya contiene {existentes:,} filas. "
            "Para evitar duplicados, deja la tabla vacía o configura "
            "service_generation.replace_existing: true."
        )

    if replace_existing and existentes:
        # No se borra automáticamente si ya hay tablas dependientes.
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM energia.medidor")
            medidores = int(cursor.fetchone()[0])

        if medidores:
            raise RuntimeError(
                "No es seguro reemplazar servicios porque energia.medidor "
                f"contiene {medidores:,} filas. Limpia primero las tablas dependientes."
            )

    sql = """
        INSERT INTO energia.servicio (
            id_servicio,
            rpu,
            id_zona,
            id_tipo_servicio,
            id_tarifa,
            nombre,
            latitud,
            longitud,
            ocupacion_estimada,
            carga_contratada_kw,
            tiene_solar
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    try:
        if replace_existing and existentes:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM energia.servicio")

        filas = construir_servicios(connection, config, rules)

        with connection.cursor() as cursor:
            for inicio in range(0, len(filas), batch_size):
                cursor.executemany(sql, filas[inicio:inicio + batch_size])

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    conteo_categorias = Counter()
    tipos = {t["id_tipo_servicio"]: t["categoria"] for t in _cargar_tipos_servicio(connection)}
    for fila in filas:
        conteo_categorias[tipos[fila[3]]] += 1

    print(f"[OK] Servicios generados: {len(filas):,}")
    for categoria in sorted(conteo_categorias):
        print(f"[OK] {categoria}: {conteo_categorias[categoria]:,}")

    return len(filas)


# Alias uniforme utilizado por main.py.
def generar(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    return generar_servicios(connection, config, rules)


if __name__ == "__main__":
    print(
        "Este archivo forma parte de HyperDataSynthetic. "
        "Ejecuta python main.py desde la raíz del proyecto."
    )
