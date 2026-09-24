import random
from datetime import timedelta

from psycopg.rows import dict_row


def obtener_seccion(config, nombre):
    """
    Obtiene una seccion del archivo de configuracion.
    """

    seccion = config.get(nombre, {})

    if isinstance(seccion, dict):
        return seccion

    return {}


def obtener_parametro(
    config,
    nombres,
    valor_default=None,
    obligatorio=False,
):
    """
    Busca un parametro usando diferentes nombres posibles.
    """

    generation = obtener_seccion(config, "generation")

    for nombre in nombres:
        if nombre in generation:
            return generation[nombre]

        if nombre in config:
            return config[nombre]

    if obligatorio:
        raise KeyError(
            "Falta uno de estos parametros: "
            + ", ".join(nombres)
        )

    return valor_default


def tabla_tiene_columna(connection, esquema, tabla, columna):
    """
    Comprueba si una tabla contiene una columna.
    """

    consulta = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND column_name = %s
        );
    """

    with connection.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                esquema,
                tabla,
                columna,
            ),
        )

        resultado = cursor.fetchone()

    return bool(resultado[0])


def obtener_columnas_tabla(connection, esquema, tabla):
    """
    Devuelve las columnas disponibles en una tabla.
    """

    consulta = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                esquema,
                tabla,
            ),
        )

        filas = cursor.fetchall()

    return [fila[0] for fila in filas]


def cargar_servicios(connection):
    """
    Obtiene los servicios directamente desde PostgreSQL.

    Ya no utiliza Servicios_generados.csv.
    """

    columnas = obtener_columnas_tabla(
        connection,
        "energia",
        "servicio",
    )

    if not columnas:
        raise RuntimeError(
            "No se encontro la tabla energia.servicio "
            "o no contiene columnas."
        )

    if "id_servicio" not in columnas:
        raise RuntimeError(
            "La tabla energia.servicio no contiene "
            "la columna id_servicio."
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
            "La tabla energia.servicio no contiene registros. "
            "Ejecuta primero el generador de servicios."
        )

    print(
        f"[OK] Servicios obtenidos desde PostgreSQL: "
        f"{len(servicios):,}"
    )

    return servicios


def obtener_fecha_instalacion(servicio, fecha_inicial):
    """
    Obtiene la fecha de instalacion disponible en el servicio.
    """

    nombres_posibles = (
        "fecha_alta",
        "fecha_inicio",
        "fecha_instalacion",
        "fecha_contratacion",
    )

    for nombre in nombres_posibles:
        valor = servicio.get(nombre)

        if valor is not None:
            return valor

    return fecha_inicial


def generar_numero_medidor(indice):
    """
    Genera un numero de medidor reproducible.
    """

    return f"HSD-TOL-{indice:08d}"


def construir_medidor(
    servicio,
    indice,
    fecha_inicial,
):
    """
    Construye la informacion basica de un medidor.
    """

    id_servicio = servicio["id_servicio"]

    fecha_instalacion = obtener_fecha_instalacion(
        servicio,
        fecha_inicial,
    )

    return {
        "id_servicio": id_servicio,
        "numero_serie": generar_numero_medidor(indice),
        "modelo": "HSD-SMART-01",
        "fabricante": "HyperDataSynthetic",
        "fecha_instalacion": fecha_instalacion,
        "fecha_retiro": None,
        "estado": "ACTIVO",
    }


def obtener_mapeo_columnas(columnas):
    """
    Determina los nombres reales de las columnas de energia.medidor.

    Permite algunas variantes comunes del esquema.
    """

    opciones = {
        "id_servicio": (
            "id_servicio",
        ),
        "numero_serie": (
            "numero_serie",
            "serie",
            "codigo_medidor",
            "numero_medidor",
        ),
        "modelo": (
            "modelo",
        ),
        "fabricante": (
            "fabricante",
            "marca",
        ),
        "fecha_instalacion": (
            "fecha_instalacion",
            "fecha_alta",
        ),
        "fecha_retiro": (
            "fecha_retiro",
            "fecha_baja",
        ),
        "estado": (
            "estado",
            "estatus",
        ),
    }

    mapeo = {}

    for campo_logico, candidatos in opciones.items():
        for candidato in candidatos:
            if candidato in columnas:
                mapeo[campo_logico] = candidato
                break

    columnas_obligatorias = (
        "id_servicio",
        "numero_serie",
    )

    faltantes = [
        nombre
        for nombre in columnas_obligatorias
        if nombre not in mapeo
    ]

    if faltantes:
        raise RuntimeError(
            "No fue posible identificar estas columnas "
            "obligatorias de energia.medidor: "
            + ", ".join(faltantes)
            + ". Columnas disponibles: "
            + ", ".join(columnas)
        )

    return mapeo


def preparar_filas_medidores(medidores, mapeo):
    """
    Convierte los medidores a las columnas reales de la tabla.
    """

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

    columnas_sql = [
        mapeo[campo]
        for campo in campos_logicos
    ]

    filas = [
        tuple(
            medidor[campo]
            for campo in campos_logicos
        )
        for medidor in medidores
    ]

    return columnas_sql, filas


def insertar_medidores(
    connection,
    medidores,
    batch_size,
):
    """
    Inserta medidores en PostgreSQL por lotes.
    """

    columnas_tabla = obtener_columnas_tabla(
        connection,
        "energia",
        "medidor",
    )

    if not columnas_tabla:
        raise RuntimeError(
            "No se encontro la tabla energia.medidor."
        )

    mapeo = obtener_mapeo_columnas(columnas_tabla)

    columnas_sql, filas = preparar_filas_medidores(
        medidores,
        mapeo,
    )

    marcadores = ", ".join(
        ["%s"] * len(columnas_sql)
    )

    nombres_columnas = ", ".join(columnas_sql)

    consulta = f"""
        INSERT INTO energia.medidor (
            {nombres_columnas}
        )
        VALUES ({marcadores});
    """

    total_insertado = 0

    with connection.cursor() as cursor:
        for inicio in range(0, len(filas), batch_size):
            lote = filas[inicio:inicio + batch_size]

            cursor.executemany(
                consulta,
                lote,
            )

            total_insertado += len(lote)

            print(
                "[OK] Medidores insertados: "
                f"{total_insertado:,}/{len(filas):,}"
            )

    return total_insertado


def generar_reemplazos(
    servicios,
    cantidad_reemplazos,
    fecha_inicial,
    fecha_final,
    indice_inicial,
    generador_aleatorio,
):
    """
    Genera medidores adicionales para representar reemplazos.

    Esta funcion solamente crea los nuevos dispositivos.
    La fecha exacta se distribuye dentro del periodo.
    """

    if cantidad_reemplazos <= 0:
        return []

    if not servicios:
        return []

    cantidad_reemplazos = min(
        cantidad_reemplazos,
        len(servicios),
    )

    servicios_seleccionados = generador_aleatorio.sample(
        servicios,
        cantidad_reemplazos,
    )

    dias_periodo = max(
        (fecha_final - fecha_inicial).days,
        1,
    )

    reemplazos = []

    for desplazamiento, servicio in enumerate(
        servicios_seleccionados,
        start=1,
    ):
        dia_reemplazo = generador_aleatorio.randint(
            1,
            dias_periodo,
        )

        fecha_reemplazo = (
            fecha_inicial
            + timedelta(days=dia_reemplazo)
        )

        indice = indice_inicial + desplazamiento

        reemplazos.append(
            {
                "id_servicio": servicio["id_servicio"],
                "numero_serie": generar_numero_medidor(indice),
                "modelo": "HSD-SMART-02",
                "fabricante": "HyperDataSynthetic",
                "fecha_instalacion": fecha_reemplazo,
                "fecha_retiro": None,
                "estado": "ACTIVO",
            }
        )

    return reemplazos


def generar_dispositivos(connection, config, rules):
    """
    Genera los medidores a partir de energia.servicio.

    Parameters
    ----------
    connection
        Conexion activa de psycopg.

    config
        Configuracion cargada desde generation.yaml.

    rules
        Reglas cargadas desde rules.yaml.

    Returns
    -------
    int
        Cantidad total de medidores insertados.
    """

    del rules

    print()
    print("=" * 60)
    print("GENERACION DE DISPOSITIVOS")
    print("=" * 60)

    semilla = int(
        obtener_parametro(
            config,
            ["seed", "semilla"],
            20260101,
        )
    )

    fecha_inicial_texto = obtener_parametro(
        config,
        [
            "start_date",
            "fecha_inicial",
            "fecha_desde",
        ],
        obligatorio=True,
    )

    fecha_final_texto = obtener_parametro(
        config,
        [
            "end_date",
            "fecha_final",
            "fecha_hasta",
        ],
        obligatorio=True,
    )

    reemplazos_habilitados = (
        obtener_seccion(config, "features")
        .get("meter_replacements", True)
    )

    cantidad_reemplazos = int(
        obtener_parametro(
            config,
            ["replacement_meters"],
            0,
        )
    )

    performance = obtener_seccion(
        config,
        "performance",
    )

    batch_size = int(
        performance.get(
            "batch_size",
            obtener_parametro(
                config,
                ["batch_size"],
                100000,
            ),
        )
    )

    from datetime import date

    fecha_inicial = date.fromisoformat(
        str(fecha_inicial_texto)
    )

    fecha_final = date.fromisoformat(
        str(fecha_final_texto)
    )

    if fecha_final < fecha_inicial:
        raise ValueError(
            "end_date no puede ser anterior a start_date."
        )

    generador_aleatorio = random.Random(semilla + 1000)

    servicios = cargar_servicios(connection)

    medidores_iniciales = [
        construir_medidor(
            servicio=servicio,
            indice=indice,
            fecha_inicial=fecha_inicial,
        )
        for indice, servicio in enumerate(
            servicios,
            start=1,
        )
    ]

    print(
        f"[OK] Medidores iniciales preparados: "
        f"{len(medidores_iniciales):,}"
    )

    reemplazos = []

    if reemplazos_habilitados and cantidad_reemplazos > 0:
        reemplazos = generar_reemplazos(
            servicios=servicios,
            cantidad_reemplazos=cantidad_reemplazos,
            fecha_inicial=fecha_inicial,
            fecha_final=fecha_final,
            indice_inicial=len(medidores_iniciales),
            generador_aleatorio=generador_aleatorio,
        )

        print(
            f"[OK] Medidores de reemplazo preparados: "
            f"{len(reemplazos):,}"
        )

    todos_los_medidores = (
        medidores_iniciales
        + reemplazos
    )

    total_insertado = insertar_medidores(
        connection=connection,
        medidores=todos_los_medidores,
        batch_size=batch_size,
    )

    print(
        f"[OK] Total de medidores generados: "
        f"{total_insertado:,}"
    )

    return total_insertado


if __name__ == "__main__":
    raise RuntimeError(
        "Dispositivos_Gen.py no debe ejecutarse directamente. "
        "Ejecuta python main.py."
    )