from pathlib import Path

import yaml

from database.connection import get_connection
from database.database_check import check_database

from Generation.Servicios_Gen import generar_servicios
from Generation.Dispositivos_Gen import generar_dispositivos
from Generation.Profile_Gen import generar_perfiles


# ======================================================================
# RUTAS DEL PROYECTO
# ======================================================================

BASE_DIR = Path(__file__).resolve().parent

GENERATION_YAML = BASE_DIR / "config" / "generation.yaml"
RULES_YAML = BASE_DIR / "config" / "rules.yaml"


# ======================================================================
# GENERADORES
# ======================================================================
#
# El orden de esta lista determina el orden de ejecución.
#
# Para agregar un generador nuevo:
#
#   1. Importarlo arriba.
#   2. Agregarlo a esta lista.
#
# Ejemplo:
#
#   ("Calendario", generar_calendario),
#
# ======================================================================

GENERADORES = [
    ("Servicios", generar_servicios),
    ("Dispositivos", generar_dispositivos),
    ("Perfiles", generar_perfiles),
]


# ======================================================================
# CONFIGURACIÓN
# ======================================================================

def cargar_yaml(ruta):
    """
    Lee un archivo YAML y devuelve su contenido.
    """

    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encontro el archivo de configuracion: {ruta}"
        )

    with open(ruta, "r", encoding="utf-8") as archivo:
        contenido = yaml.safe_load(archivo)

    if contenido is None:
        raise ValueError(
            f"El archivo de configuracion esta vacio: {ruta}"
        )

    return contenido


def cargar_configuracion():
    """
    Carga los archivos de configuracion utilizados por la generacion.
    """

    print()
    print("⚙️ Cargando configuracion...")

    generation_config = cargar_yaml(GENERATION_YAML)
    rules_config = cargar_yaml(RULES_YAML)

    print("✅ generation.yaml")
    print("✅ rules.yaml")

    return generation_config, rules_config


# ======================================================================
# GENERADORES
# ======================================================================

def ejecutar_generadores(connection, config, rules):
    """
    Ejecuta todos los generadores registrados en GENERADORES.
    """

    total = len(GENERADORES)

    print()
    print("=" * 60)
    print("🏭 GENERACION DE DATOS")
    print("=" * 60)

    for numero, (nombre, generador) in enumerate(
        GENERADORES,
        start=1
    ):

        print()
        print("-" * 60)
        print(f"[{numero}/{total}] {nombre}")
        print("-" * 60)

        try:

            generador(
                connection=connection,
                config=config,
                rules=rules,
            )

            print()
            print(f"✅ {nombre} completado")

        except Exception as error:

            print()
            print(f"❌ Error en el generador: {nombre}")
            print(f"   {error}")

            raise


# ======================================================================
# MAIN
# ======================================================================

def main():

    connection = None

    print()
    print("=" * 60)
    print("⚡ HYPERDATASYNTHETIC")
    print("=" * 60)

    try:

        # ==============================================================
        # 1. CARGAR CONFIGURACIÓN
        # ==============================================================

        config, rules = cargar_configuracion()

        print()
        print("✅ Configuracion cargada correctamente")


        # ==============================================================
        # 2. CONECTAR CON POSTGRESQL
        # ==============================================================

        print()
        print("🐘 Conectando con PostgreSQL...")

        connection = get_connection()

        print("✅ Conexion establecida")


        # ==============================================================
        # 3. VALIDAR BASE DE DATOS
        # ==============================================================

        print()
        print("🔍 Verificando base de datos...")

        check_database(connection)

        print("✅ Base de datos preparada")


        # ==============================================================
        # 4. EJECUTAR GENERADORES
        # ==============================================================

        ejecutar_generadores(
            connection=connection,
            config=config,
            rules=rules,
        )


        # ==============================================================
        # 5. FINALIZAR
        # ==============================================================

        print()
        print("=" * 60)
        print("✅ GENERACION FINALIZADA")
        print("=" * 60)


    except KeyboardInterrupt:

        print()
        print()
        print("=" * 60)
        print("⚠️ GENERACION CANCELADA POR EL USUARIO")
        print("=" * 60)


    except Exception as error:

        print()
        print("=" * 60)
        print("❌ GENERACION INTERRUMPIDA")
        print("=" * 60)
        print()
        print(f"Error: {error}")


    finally:

        if connection is not None:

            try:
                connection.close()
                print()
                print("🔌 Conexion PostgreSQL cerrada")

            except Exception:
                pass


# ======================================================================
# PUNTO DE ENTRADA
# ======================================================================

if __name__ == "__main__":
    main()