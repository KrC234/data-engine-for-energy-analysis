import sys

from config.settings import settings
from database.connection import test_connection
from database.database_check import check_database


def print_header():
    print()
    print("=" * 60)
    print(" HYPER DATA SYNTHETIC")
    print("=" * 60)
    print()


def main():

    print_header()

    try:

        # ============================================
        # CONFIGURACION
        # ============================================

        print("[1/3] Validando configuracion...")

        settings.validate()

        print("[OK] Configuracion valida")
        print()


        # ============================================
        # POSTGRESQL
        # ============================================

        print("[2/3] Conectando con PostgreSQL...")

        info = test_connection()

        print("[OK] Conexion establecida")
        print(f"     Base:    {info['database']}")
        print(f"     Usuario: {info['user']}")
        print()


        # ============================================
        # ESQUEMA
        # ============================================

        print("[3/3] Verificando esquema...")

        status = check_database()

        print(
            f"[INFO] Tablas requeridas encontradas: "
            f"{status['found_count']}/{status['required']}"
        )

        if not status["valid"]:

            print()
            print("[ERROR] Faltan tablas:")

            for table in sorted(status["missing"]):
                print(f"       - {table}")

            sys.exit(1)

        print("[OK] Esquema PostgreSQL completo")

        print()
        print("=" * 60)
        print(" SISTEMA LISTO")
        print("=" * 60)
        print()

    except Exception as exc:

        print()
        print("[ERROR] HyperDataSynthetic no pudo iniciar")
        print(f"[ERROR] {exc}")
        print()

        sys.exit(1)


if __name__ == "__main__":
    main()