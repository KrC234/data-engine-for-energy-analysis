"""
GENERADOR DE DISPOSITIVOS / MEDIDORES
Generation/Dispositivos_Gen.py

Genera un medidor inicial por cada servicio existente en PostgreSQL y,
opcionalmente, medidores de reemplazo.

Mejoras incorporadas:
- Usa rules.yaml -> meters -> brands para asignar marcas con pesos.
- Conserva un generador aleatorio local y reproducible.
- Genera numeros de serie con prefijo de marca, anio y secuencial.
- Mantiene compatibilidad con variantes comunes del esquema SQL.
- Retira el medidor anterior cuando se genera un reemplazo.
- Respeta el rango completo de fechas configurado.
- No ejecuta commit internamente; main.py controla la transaccion.
"""

import random
from datetime import date, datetime, timedelta

from psycopg import sql
from psycopg.rows import dict_row


# ======================================================================
# CONFIGURACION
# ======================================================================


def obtener_seccion(config, nombre):
    """Obtiene una seccion del archivo de configuracion."""
    seccion = config.get(nombre, {})
    return seccion if isinstance(seccion, dict) else {}


def obtener_parametro(config, nombres, valor_default=None, obligatorio=False):
    """Busca un parametro en generation y en la raiz de config."""
    generation = obtener_seccion(config, "generation")

    for nombre in nombres:
        if nombre in generation and generation[nombre] is not None:
            return generation[nombre]
        if nombre in config and config[nombre] is not None:
            return config[nombre]

    if obligatorio:
        raise KeyError("Falta uno de estos parametros: " + ", ".join(nombres))

    return valor_default


def convertir_fecha(valor, nombre_parametro):
    """Convierte date, datetime o texto ISO a date."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"El parametro {nombre_parametro} debe tener formato YYYY-MM-DD: {valor!r}"
        ) from error


def obtener_reglas_medidores(rules):
    """Obtiene y valida rules.yaml -> meters."""
    reglas = obtener_seccion(rules, "meters")
    if not reglas:
        raise KeyError("Falta la seccion 'meters' en rules.yaml.")
    return reglas


def obtener_marcas(reglas_meters):
    """Valida la distribucion de marcas y devuelve nombres y pesos."""
    marcas = reglas_meters.get("brands")

    if not isinstance(marcas, dict) or not marcas:
        raise ValueError(
            "rules.yaml debe contener meters.brands con al menos una marca."
        )

    nombres = []
    pesos = []

    for marca, peso in marcas.items():
        nombre = str(marca).strip().upper()
        try:
            peso_numerico = float(peso)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"El peso de la marca {marca!r} no es numerico: {peso!r}"
            ) from error

        if not nombre:
            raise ValueError("No se permiten nombres de marca vacios.")
        if peso_numerico < 0:
            raise ValueError(f"El peso de {nombre} no puede ser negativo.")

        nombres.append(nombre)
        pesos.append(peso_numerico)

    if sum(pesos) <= 0:
        raise ValueError("La suma de los pesos de meters.brands debe ser mayor que cero.")

    return nombres, pesos


def elegir_marca(generador_aleatorio, nombres, pesos):
    """Elige una marca respetando los pesos configurados."""
    return generador_aleatorio.choices(nombres, weights=pesos, k=1)[0]


# ======================================================================
# METADATOS DE POSTGRESQL
# ======================================================================


def obtener_columnas_tabla(connection, esquema, tabla):
    """Devuelve las columnas disponibles en una tabla."""
    consulta = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(consulta, (esquema, tabla))
        filas = cursor.fetchall()

    return [fila[0] for fila in filas]


def cargar_servicios(connection):
    """Carga los servicios desde energia.servicio."""
    columnas = obtener_columnas_tabla(connection, "energia", "servicio")

    if not columnas:
        raise RuntimeError(
            "No se encontro la tabla energia.servicio o no contiene columnas."
        )
    if "id_servicio" not in columnas:
        raise RuntimeError(
            "La tabla energia.servicio no contiene la columna id_servicio."
        )

    consulta = """
        SELECT *
        FROM energia.servicio
        ORDER BY id_servicio;
    """

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(consulta)
        servicios = cursor.fetchall()

    if not servicios:
        raise RuntimeError(
            "energia.servicio no contiene registros. Ejecuta primero Servicios_Gen.py."
        )

    print(f"[OK] Servicios obtenidos desde PostgreSQL: {len(servicios):,}")
    return servicios


# ======================================================================
# CONSTRUCCION DE MEDIDORES
# ======================================================================


def obtener_fecha_instalacion(servicio, fecha_inicial):
    """Usa la fecha disponible del servicio o la fecha inicial de la corrida."""
    for nombre in (
        "fecha_alta",
        "fecha_inicio",
        "fecha_instalacion",
        "fecha_contratacion",
    ):
        valor = servicio.get(nombre)
        if valor is not None:
            return convertir_fecha(valor, nombre)

    return fecha_inicial


def generar_numero_medidor(marca, indice, fecha_referencia):
    """
    Genera una serie unica y reproducible de hasta 24 caracteres.

    Ejemplo: MEDI-2600000001-8
    """
    prefijo = "".join(c for c in marca.upper() if c.isalnum())[:4]
    prefijo = (prefijo or "HSD").ljust(4, "X")
    anio = str(fecha_referencia.year)[-2:]
    base = f"{prefijo}-{anio}{indice:08d}"
    digito = sum(ord(caracter) for caracter in base) % 10
    return f"{base}-{digito}"


def construir_medidor(
    servicio,
    indice,
    fecha_inicial,
    generador_aleatorio,
    nombres_marcas,
    pesos_marcas,
    modelo="HSD-SMART-01",
):
    """Construye un medidor inicial."""
    fecha_instalacion = obtener_fecha_instalacion(servicio, fecha_inicial)
    marca = elegir_marca(generador_aleatorio, nombres_marcas, pesos_marcas)

    return {
        "id_servicio": servicio["id_servicio"],
        "numero_serie": generar_numero_medidor(marca, indice, fecha_instalacion),
        "modelo": modelo,
        "fabricante": marca,
        "fecha_instalacion": fecha_instalacion,
        "fecha_retiro": None,
        "estado": "ACTIVO",
    }


def generar_reemplazos(
    servicios,
    cantidad_reemplazos,
    fecha_inicial,
    fecha_final,
    indice_inicial,
    generador_aleatorio,
    nombres_marcas,
    pesos_marcas,
):
    """
    Genera medidores de reemplazo y devuelve parejas:
    (medidor_nuevo, fecha_reemplazo).
    """
    if cantidad_reemplazos <= 0 or not servicios:
        return []

    cantidad = min(cantidad_reemplazos, len(servicios))
    servicios_seleccionados = generador_aleatorio.sample(servicios, cantidad)
    dias_periodo = (fecha_final - fecha_inicial).days
    reemplazos = []

    for desplazamiento, servicio in enumerate(servicios_seleccionados, start=1):
        # Si existe al menos un dia de rango, nunca reemplaza antes del inicio.
        dia_reemplazo = generador_aleatorio.randint(1, dias_periodo) if dias_periodo else 0
        fecha_reemplazo = fecha_inicial + timedelta(days=dia_reemplazo)
        indice = indice_inicial + desplazamiento
        marca = elegir_marca(generador_aleatorio, nombres_marcas, pesos_marcas)

        nuevo = {
            "id_servicio": servicio["id_servicio"],
            "numero_serie": generar_numero_medidor(marca, indice, fecha_reemplazo),
            "modelo": "HSD-SMART-02",
            "fabricante": marca,
            "fecha_instalacion": fecha_reemplazo,
            "fecha_retiro": None,
            "estado": "ACTIVO",
        }
        reemplazos.append((nuevo, fecha_reemplazo))

    return reemplazos


# ======================================================================
# MAPEO E INSERCION
# ======================================================================


def obtener_mapeo_columnas(columnas):
    """Relaciona campos logicos con las columnas reales de energia.medidor."""
    opciones = {
        "id_servicio": ("id_servicio",),
        "numero_serie": ("numero_serie", "serie", "codigo_medidor", "numero_medidor"),
        "modelo": ("modelo",),
        "fabricante": ("fabricante", "marca"),
        "fecha_instalacion": ("fecha_instalacion", "fecha_alta"),
        "fecha_retiro": ("fecha_retiro", "fecha_baja"),
        "estado": ("estado", "estatus"),
    }

    mapeo = {}
    for campo_logico, candidatos in opciones.items():
        for candidato in candidatos:
            if candidato in columnas:
                mapeo[campo_logico] = candidato
                break

    faltantes = [
        campo for campo in ("id_servicio", "numero_serie") if campo not in mapeo
    ]
    if faltantes:
        raise RuntimeError(
            "No fue posible identificar columnas obligatorias de energia.medidor: "
            + ", ".join(faltantes)
            + ". Columnas disponibles: "
            + ", ".join(columnas)
        )

    return mapeo


def preparar_filas_medidores(medidores, mapeo):
    """Convierte los diccionarios a las columnas reales de la tabla."""
    campos_logicos = [
        campo
        for campo in (
            "id_servicio",
            "numero_serie",
            "modelo",
            "fabricante",
            "fecha_instalacion",
            "fecha_retiro",
            "estado",
        )
        if campo in mapeo
    ]
    columnas_sql = [mapeo[campo] for campo in campos_logicos]
    filas = [tuple(medidor[campo] for campo in campos_logicos) for medidor in medidores]
    return columnas_sql, filas


def insertar_medidores(connection, medidores, batch_size, mapeo=None):
    """Inserta medidores por lotes y devuelve la cantidad insertada."""
    if not medidores:
        return 0
    if batch_size <= 0:
        raise ValueError("batch_size debe ser mayor que cero.")

    if mapeo is None:
        columnas = obtener_columnas_tabla(connection, "energia", "medidor")
        if not columnas:
            raise RuntimeError("No se encontro la tabla energia.medidor.")
        mapeo = obtener_mapeo_columnas(columnas)

    columnas_sql, filas = preparar_filas_medidores(medidores, mapeo)
    consulta = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
        sql.Identifier("energia"),
        sql.Identifier("medidor"),
        sql.SQL(", ").join(map(sql.Identifier, columnas_sql)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columnas_sql),
    )

    total_insertado = 0
    with connection.cursor() as cursor:
        for inicio in range(0, len(filas), batch_size):
            lote = filas[inicio : inicio + batch_size]
            cursor.executemany(consulta, lote)
            total_insertado += len(lote)
            print(f"[OK] Medidores insertados: {total_insertado:,}/{len(filas):,}")

    return total_insertado


def retirar_medidores_reemplazados(connection, reemplazos, mapeo):
    """Marca como retirado el medidor activo anterior de cada servicio."""
    if not reemplazos:
        return 0
    if "fecha_retiro" not in mapeo and "estado" not in mapeo:
        raise RuntimeError(
            "No se pueden aplicar reemplazos: energia.medidor no tiene "
            "fecha_retiro/fecha_baja ni estado/estatus."
        )

    asignaciones = []
    if "fecha_retiro" in mapeo:
        asignaciones.append(
            sql.SQL("{} = %s").format(sql.Identifier(mapeo["fecha_retiro"]))
        )
    if "estado" in mapeo:
        asignaciones.append(
            sql.SQL("{} = %s").format(sql.Identifier(mapeo["estado"]))
        )

    filtros_activo = []
    if "fecha_retiro" in mapeo:
        filtros_activo.append(
            sql.SQL("{} IS NULL").format(sql.Identifier(mapeo["fecha_retiro"]))
        )
    if "estado" in mapeo:
        filtros_activo.append(
            sql.SQL("{} = %s").format(sql.Identifier(mapeo["estado"]))
        )

    consulta = sql.SQL("UPDATE {}.{} SET {} WHERE {} = %s").format(
        sql.Identifier("energia"),
        sql.Identifier("medidor"),
        sql.SQL(", ").join(asignaciones),
        sql.Identifier(mapeo["id_servicio"]),
    )
    if filtros_activo:
        consulta += sql.SQL(" AND ") + sql.SQL(" AND ").join(filtros_activo)

    total_actualizado = 0
    with connection.cursor() as cursor:
        for medidor_nuevo, fecha_reemplazo in reemplazos:
            parametros = []
            if "fecha_retiro" in mapeo:
                parametros.append(fecha_reemplazo)
            if "estado" in mapeo:
                parametros.append("RETIRADO")
            parametros.append(medidor_nuevo["id_servicio"])
            if "estado" in mapeo:
                parametros.append("ACTIVO")

            cursor.execute(consulta, tuple(parametros))
            total_actualizado += cursor.rowcount

    return total_actualizado


# ======================================================================
# GENERADOR PRINCIPAL
# ======================================================================


def generar_dispositivos(connection, config, rules):
    """Genera e inserta medidores iniciales y reemplazos."""
    print()
    print("=" * 60)
    print("GENERACION DE DISPOSITIVOS")
    print("=" * 60)

    semilla = int(obtener_parametro(config, ["seed", "semilla"], 20260101))
    fecha_inicial = convertir_fecha(
        obtener_parametro(
            config,
            ["start_date", "date_start", "fecha_inicial", "fecha_inicio", "fecha_desde"],
            obligatorio=True,
        ),
        "start_date/date_start",
    )
    fecha_final = convertir_fecha(
        obtener_parametro(
            config,
            ["end_date", "date_end", "fecha_final", "fecha_fin", "fecha_hasta"],
            obligatorio=True,
        ),
        "end_date/date_end",
    )

    if fecha_final < fecha_inicial:
        raise ValueError("La fecha final no puede ser anterior a la fecha inicial.")

    features = obtener_seccion(config, "features")
    reemplazos_habilitados = features.get("meter_replacements", True)
    cantidad_reemplazos = int(
        obtener_parametro(config, ["replacement_meters", "medidores_reemplazo"], 0)
    )
    if cantidad_reemplazos < 0:
        raise ValueError("replacement_meters no puede ser negativo.")

    performance = obtener_seccion(config, "performance")
    batch_size = int(
        performance.get(
            "batch_size",
            obtener_parametro(config, ["batch_size", "tamano_lote"], 100000),
        )
    )

    reglas_meters = obtener_reglas_medidores(rules)
    nombres_marcas, pesos_marcas = obtener_marcas(reglas_meters)
    generador_aleatorio = random.Random(semilla + 1000)

    print("[OK] Marcas configuradas: " + ", ".join(nombres_marcas))

    columnas_medidor = obtener_columnas_tabla(connection, "energia", "medidor")
    if not columnas_medidor:
        raise RuntimeError("No se encontro la tabla energia.medidor.")
    mapeo = obtener_mapeo_columnas(columnas_medidor)

    servicios = cargar_servicios(connection)
    medidores_iniciales = [
        construir_medidor(
            servicio=servicio,
            indice=indice,
            fecha_inicial=fecha_inicial,
            generador_aleatorio=generador_aleatorio,
            nombres_marcas=nombres_marcas,
            pesos_marcas=pesos_marcas,
        )
        for indice, servicio in enumerate(servicios, start=1)
    ]

    print(f"[OK] Medidores iniciales preparados: {len(medidores_iniciales):,}")
    total_insertado = insertar_medidores(
        connection, medidores_iniciales, batch_size, mapeo
    )

    if reemplazos_habilitados and cantidad_reemplazos > 0:
        reemplazos = generar_reemplazos(
            servicios=servicios,
            cantidad_reemplazos=cantidad_reemplazos,
            fecha_inicial=fecha_inicial,
            fecha_final=fecha_final,
            indice_inicial=len(medidores_iniciales),
            generador_aleatorio=generador_aleatorio,
            nombres_marcas=nombres_marcas,
            pesos_marcas=pesos_marcas,
        )

        actualizados = retirar_medidores_reemplazados(connection, reemplazos, mapeo)
        nuevos = [medidor for medidor, _ in reemplazos]
        total_insertado += insertar_medidores(connection, nuevos, batch_size, mapeo)

        print(f"[OK] Medidores anteriores retirados: {actualizados:,}")
        print(f"[OK] Medidores de reemplazo insertados: {len(nuevos):,}")
    else:
        print("[OK] No se solicitaron reemplazos de medidor")

    print(f"[OK] Total de medidores insertados: {total_insertado:,}")
    return total_insertado


if __name__ == "__main__":
    raise RuntimeError(
        "Dispositivos_Gen.py no debe ejecutarse directamente. Ejecuta python main.py."
    )
