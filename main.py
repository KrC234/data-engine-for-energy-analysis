from pathlib import Path

import yaml

from database.connection import get_connection
from database.database_check import check_database

from Generation.Calendario_Gen import generar_calendario
from Generation.Profile_Gen import generar_perfiles
from Generation.Servicios_Gen import generar_servicios
from Generation.Dispositivos_Gen import generar_dispositivos
from Generation.Eventos_Gen import generar_eventos
from Generation.Lecturas_Gen import generar_lecturas
from Generation.Alertas_Gen import generar_alertas
from Generation.Facturacion_Gen import generar_facturacion


# ======================================================================
# RUTAS DEL PROYECTO
# ======================================================================

BASE_DIR = Path(__file__).resolve().parent

GENERATION_YAML = BASE_DIR / "config" / "generation.yaml"
RULES_YAML = BASE_DIR / "config" / "rules.yaml"


# ======================================================================
# GENERADORES
# ======================================================================

GENERADORES = [
    ("Calendario", generar_calendario),
    ("Perfiles", generar_perfiles),
    ("Servicios", generar_servicios),
    ("Dispositivos", generar_dispositivos),
    ("Eventos", generar_eventos),
    ("Lecturas", generar_lecturas),
    ("Alertas", generar_alertas),
    ("Facturacion", generar_facturacion),
]


# ======================================================================
# CARGAR ARCHIVO YAML
# ======================================================================

def cargar_yaml(ruta):
    """
    Lee un archivo YAML y devuelve su contenido como diccionario.
    """

    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encontro el archivo de configuracion: {ruta}"
        )

    if not ruta.is_file():
        raise FileNotFoundError(
            f"La ruta indicada no corresponde a un archivo: {ruta}"
        )

    try:
        with ruta.open("r", encoding="utf-8") as archivo:
            contenido = yaml.safe_load(archivo)

    except yaml.YAMLError as error:
        raise ValueError(
            "El archivo YAML contiene un error:\n"
            f"{ruta}\n\n"
            f"Detalle:\n{error}"
        ) from error

    if contenido is None:
        raise ValueError(
            f"El archivo de configuracion esta vacio: {ruta}"
        )

    if not isinstance(contenido, dict):
        raise ValueError(
            "El contenido principal del archivo YAML debe ser "
            f"un diccionario: {ruta}"
        )

    return contenido


# ======================================================================
# CARGAR CONFIGURACION
# ======================================================================

def cargar_configuracion():
    """
    Carga generation.yaml y rules.yaml.
    """

    print()
    print("Cargando configuracion...")

    generation_config = cargar_yaml(GENERATION_YAML)
    rules_config = cargar_yaml(RULES_YAML)

    print("[OK] generation.yaml")
    print("[OK] rules.yaml")

    return generation_config, rules_config


# ======================================================================
# UTILIDADES DE CONFIGURACION
# ======================================================================

def obtener_seccion_generacion(config):
    """
    Obtiene la seccion principal de generacion.
    """

    generation = config.get("generation")

    if isinstance(generation, dict):
        return generation

    return config


def obtener_parametro(config, nombres, valor_default="No definido"):
    """
    Busca un parametro utilizando diferentes nombres posibles.
    """

    for nombre in nombres:
        if nombre in config:
            valor = config[nombre]

            if valor is not None:
                return valor

    return valor_default


def mostrar_configuracion(config):
    """
    Muestra los parametros principales de la generacion.
    """

    generation = obtener_seccion_generacion(config)

    nombre = obtener_parametro(
        generation,
        ["name", "nombre"],
        "Corrida sin nombre",
    )

    semilla = obtener_parametro(
        generation,
        ["seed", "semilla"],
    )

    fecha_inicial = obtener_parametro(
        generation,
        [
            "start_date",
            "fecha_inicial",
            "fecha_inicio",
            "fecha_desde",
        ],
    )

    fecha_final = obtener_parametro(
        generation,
        [
            "end_date",
            "fecha_final",
            "fecha_fin",
            "fecha_hasta",
        ],
    )

    intervalo = obtener_parametro(
        generation,
        [
            "reading_interval_minutes",
            "interval_minutes",
            "intervalo_min",
            "intervalo_minutos",
        ],
    )

    servicios = obtener_parametro(
        generation,
        [
            "services",
            "service_count",
            "numero_servicios",
            "total_servicios",
        ],
    )

    batch_size = obtener_parametro(
        generation,
        [
            "batch_size",
            "tamano_lote",
        ],
    )

    print()
    print("=" * 60)
    print("CONFIGURACION DE LA CORRIDA")
    print("=" * 60)
    print(f"Nombre ............... {nombre}")
    print(f"Semilla .............. {semilla}")
    print(f"Fecha inicial ........ {fecha_inicial}")
    print(f"Fecha final .......... {fecha_final}")
    print(f"Intervalo ............ {intervalo} minutos")
    print(f"Servicios ............ {servicios}")
    print(f"Tamano de lote ....... {batch_size}")
    print("=" * 60)


# ======================================================================
# EJECUTAR UN GENERADOR
# ======================================================================

def ejecutar_un_generador(
    nombre,
    generador,
    connection,
    config,
    rules,
):
    """
    Ejecuta un generador.

    Primero intenta llamarlo con connection, config y rules.
    Si el generador no acepta esos parametros, intenta ejecutarlo
    sin argumentos.
    """

    try:
        return generador(
            connection=connection,
            config=config,
            rules=rules,
        )

    except TypeError as error:
        mensaje = str(error)

        errores_de_firma = (
            "unexpected keyword argument",
            "takes 0 positional arguments",
            "required positional argument",
        )

        if not any(texto in mensaje for texto in errores_de_firma):
            raise

        print(
            f"[AVISO] {nombre} no acepta connection, config y rules."
        )
        print(
            f"[AVISO] Ejecutando {nombre} sin argumentos."
        )

        return generador()


# ======================================================================
# EJECUTAR GENERADORES
# ======================================================================

def ejecutar_generadores(connection, config, rules):
    """
    Ejecuta todos los generadores registrados.
    """

    if not GENERADORES:
        raise RuntimeError(
            "No hay generadores registrados en GENERADORES"
        )

    total_generadores = len(GENERADORES)
    resultados = []

    print()
    print("=" * 60)
    print("GENERACION DE DATOS")
    print("=" * 60)

    for numero, (nombre, generador) in enumerate(
        GENERADORES,
        start=1,
    ):
        print()
        print("-" * 60)
        print(f"[{numero}/{total_generadores}] {nombre}")
        print("-" * 60)

        try:
            resultado = ejecutar_un_generador(
                nombre=nombre,
                generador=generador,
                connection=connection,
                config=config,
                rules=rules,
            )

            resultados.append(
                {
                    "nombre": nombre,
                    "estado": "COMPLETADO",
                    "registros": resultado,
                }
            )

            print()
            print(f"[OK] {nombre} completado")

            if (
                isinstance(resultado, int)
                and not isinstance(resultado, bool)
            ):
                print(
                    f"     Registros procesados: {resultado:,}"
                )

        except KeyboardInterrupt:
            print()
            print(f"[CANCELADO] {nombre}")
            raise

        except Exception as error:
            resultados.append(
                {
                    "nombre": nombre,
                    "estado": "ERROR",
                    "registros": None,
                }
            )

            print()
            print(f"[ERROR] Fallo el generador: {nombre}")
            print(f"Tipo de error: {type(error).__name__}")
            print(f"Detalle: {error}")

            raise

    return resultados


# ======================================================================
# MOSTRAR RESUMEN
# ======================================================================

def mostrar_resumen(resultados):
    """
    Muestra el resultado de los generadores ejecutados.
    """

    print()
    print("=" * 60)
    print("RESUMEN DE LA GENERACION")
    print("=" * 60)

    if not resultados:
        print("No hay resultados para mostrar.")
        print("=" * 60)
        return

    for resultado in resultados:
        nombre = resultado["nombre"]
        estado = resultado["estado"]
        registros = resultado["registros"]

        if estado == "COMPLETADO":
            marca = "[OK]"
        else:
            marca = "[ERROR]"

        if (
            isinstance(registros, int)
            and not isinstance(registros, bool)
        ):
            detalle = f"{registros:,} registros"
        else:
            detalle = estado

        print(f"{marca} {nombre:.<30} {detalle}")

    print("=" * 60)


# ======================================================================
# ROLLBACK
# ======================================================================

def revertir_transaccion(connection):
    """
    Revierte la transaccion actual.
    """

    if connection is None:
        return

    try:
        connection.rollback()

        print()
        print("[OK] Transaccion actual revertida")

    except Exception as error:
        print()
        print(
            "[ADVERTENCIA] No fue posible ejecutar rollback: "
            f"{error}"
        )


# ======================================================================
# CERRAR CONEXION
# ======================================================================

def cerrar_conexion(connection):
    """
    Cierra la conexion con PostgreSQL.
    """

    if connection is None:
        return

    try:
        connection.close()

        print()
        print("[OK] Conexion PostgreSQL cerrada")

    except Exception as error:
        print()
        print(
            "[ADVERTENCIA] No fue posible cerrar la conexion: "
            f"{error}"
        )


# ======================================================================
# MAIN
# ======================================================================

def main():
    """
    Punto principal de ejecucion de HyperDataSynthetic.
    """

    connection = None
    resultados = []

    print()
    print("=" * 60)
    print("HYPERDATASYNTHETIC")
    print("=" * 60)

    try:
        # ==============================================================
        # 1. CARGAR CONFIGURACION
        # ==============================================================

        config, rules = cargar_configuracion()

        print()
        print("[OK] Configuracion cargada correctamente")

        mostrar_configuracion(config)

        # ==============================================================
        # 2. CONECTAR CON POSTGRESQL
        # ==============================================================

        print()
        print("Conectando con PostgreSQL...")

        connection = get_connection()

        if connection is None:
            raise ConnectionError(
                "get_connection() no devolvio una conexion valida"
            )

        print("[OK] Conexion establecida")

        # ==============================================================
        # 3. VALIDAR BASE DE DATOS
        # ==============================================================
        #
        # CORREGIDO:
        #
        # La funcion check_database no recibe argumentos.
        #
        # Antes:
        #     check_database(connection)
        #
        # Ahora:
        #     check_database()
        # ==============================================================

        print()
        print("Verificando base de datos...")

        check_database()

        print("[OK] Base de datos preparada")

        # ==============================================================
        # 4. EJECUTAR GENERADORES
        # ==============================================================

        resultados = ejecutar_generadores(
            connection=connection,
            config=config,
            rules=rules,
        )

        # ==============================================================
        # 5. CONFIRMAR TRANSACCION
        # ==============================================================

        connection.commit()

        print()
        print("[OK] Transaccion confirmada")

        # ==============================================================
        # 6. MOSTRAR RESUMEN
        # ==============================================================

        mostrar_resumen(resultados)

        # ==============================================================
        # 7. FINALIZAR
        # ==============================================================

        print()
        print("=" * 60)
        print("[OK] GENERACION FINALIZADA")
        print("=" * 60)

        return 0

    except KeyboardInterrupt:
        print()
        print()
        print("=" * 60)
        print("[CANCELADO] GENERACION CANCELADA POR EL USUARIO")
        print("=" * 60)

        revertir_transaccion(connection)

        return 130

    except FileNotFoundError as error:
        print()
        print("=" * 60)
        print("[ERROR] ARCHIVO NO ENCONTRADO")
        print("=" * 60)
        print()
        print(error)

        revertir_transaccion(connection)

        return 1

    except ValueError as error:
        print()
        print("=" * 60)
        print("[ERROR] CONFIGURACION O DATOS INVALIDOS")
        print("=" * 60)
        print()
        print(error)

        revertir_transaccion(connection)

        return 1

    except ConnectionError as error:
        print()
        print("=" * 60)
        print("[ERROR] CONEXION CON POSTGRESQL")
        print("=" * 60)
        print()
        print(error)

        revertir_transaccion(connection)

        return 1

    except Exception as error:
        print()
        print("=" * 60)
        print("[ERROR] GENERACION INTERRUMPIDA")
        print("=" * 60)
        print()
        print(f"Tipo de error: {type(error).__name__}")
        print(f"Detalle: {error}")

        revertir_transaccion(connection)

        return 1

    finally:
        cerrar_conexion(connection)


# ======================================================================
# PUNTO DE ENTRADA
# ======================================================================
#
# ESTE BLOQUE ES OBLIGATORIO.
# SIN ESTE BLOQUE, PYTHON NO EJECUTA main().
# ======================================================================

if __name__ == "__main__":
    print("[INICIO] Ejecutando HyperDataSynthetic")
    codigo_salida = main()
    raise SystemExit(codigo_salida)