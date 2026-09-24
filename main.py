"""
    HYPERDATASYNTHETIC - ORQUESTADOR DE GENERACION (main.py)

    Ejecuta la generacion completa de datos sinteticos:

        1. Calendario        (energia.calendario)
        2. Servicios         (energia.servicio)
        3. Medidores         (energia.medidor + reemplazos)
        4. Eventos + Alertas (energia.evento, energia.alerta)
        5. Lecturas          (energia.lectura, en lotes de 100,000 con COPY)
        6. Periodos          (energia.periodo_facturacion)

    Uso:

        python main.py                     # corrida completa (5,000 x 90 dias)
        python main.py --demo              # 60 servicios x 90 dias = 129,600
                                           # lecturas en 2 lotes de COPY
        python main.py --servicios 200 --dias 7
        python main.py --reset             # limpia hechos antes de generar

    Los parametros de la corrida se definen en config/generation.yaml
    y las probabilidades en config/rules.yaml.
"""

import argparse
import hashlib
import sys
from datetime import date, datetime, timedelta

import yaml

from config.settings import settings, BASE_DIR
from database.connection import get_connection
from database.database_check import check_database
from database.insertar import copy_lote
from Generation.Calendario_Gen import generar_calendario
from Generation.Servicios.Servicios_Gen import generar_servicios
from Generation.Servicios.Dispositivos_Gen import generar_medidores
from Generation.Lecturas_Gen import generar_lecturas
from Generation.Periodos_Gen import generar_periodos
from Generation.Perfil_de_carga.Profile_Gen import verificar_perfiles


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------

def cargar_yaml(ruta):
    with open(ruta, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def leer_int(prompt, default):
    try:
        return int(input(prompt))
    except (ValueError, EOFError):
        return default


def _separador(titulo):
    print("\n" + "=" * 72)
    print(f"  {titulo}")
    print("=" * 72)


def _fin_de_mes(mes):
    if mes.month == 12:
        return date(mes.year, 12, 31)
    import calendar as _cal
    ultimo = _cal.monthrange(mes.year, mes.month)[1]
    return date(mes.year, mes.month, ultimo)


# ----------------------------------------------------------------------
# Preparacion de la corrida
# ----------------------------------------------------------------------

def crear_corrida(connection, config, hash_params):
    """Crea el registro base en energia.corrida_generacion."""
    with connection.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(id_corrida), 0) + 1 FROM energia.corrida_generacion")
        id_corrida = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO energia.corrida_generacion
                (id_corrida, nombre, semilla, version_reglas, hash_parametros,
                 ts_inicio_ejecucion, fecha_desde, fecha_hasta, intervalo_min)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                id_corrida,
                config["generation"]["name"][:40],
                config["generation"]["seed"],
                config["generation"]["rules_version"],
                hash_params,
                datetime.now().isoformat(),
                config["generation"]["date_start"],
                config["generation"]["date_end"],
                config["generation"]["interval_minutes"],
            ),
        )
    connection.commit()
    return id_corrida


def cerrar_corrida(connection, id_corrida, total_lecturas):
    """Actualiza total de lecturas y cierre de la corrida."""
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE energia.corrida_generacion
            SET ts_fin_ejecucion = %s, total_lecturas = %s
            WHERE id_corrida = %s
            """,
            (datetime.now().isoformat(), total_lecturas, id_corrida),
        )
    connection.commit()


def limpiar_hechos(connection):
    """Borra los datos de hechos previos (nota: no los catalogos).
    Con --reset en desarrollo tambien se limpia el historial de corridas
    para permitir re-ejecutar el mismo escenario sin friccion."""
    orden = [
        "alerta",
        "periodo_facturacion",
        "lectura",
        "evento",
        "medidor",
        "servicio",
        "calendario",
        "corrida_generacion",
    ]
    with connection.cursor() as cur:
        for tabla in orden:
            cur.execute(f"TRUNCATE energia.{tabla} RESTART IDENTITY CASCADE")
    connection.commit()
    print("    Hechos previos eliminados (TRUNCATE CASCADE, incluye corrida)")


def hash_params(config):
    texto = (
        f"{config['generation']['seed']}|"
        f"{config['generation']['rules_version']}|"
        f"{config['generation']['services']}|"
        f"{config['generation']['date_start']}|"
        f"{config['generation']['date_end']}|"
        f"{config['generation']['interval_minutes']}|"
        f"{config['performance']['batch_size']}"
    )
    return hashlib.sha256(texto.encode()).hexdigest()


# ----------------------------------------------------------------------
# Validacion final
# ----------------------------------------------------------------------

def validar(connection, config, total_lecturas):
    _separador("VALIDACION")

    con = {}
    with connection.cursor() as cur:
        for tabla in [
            "calendario",
            "servicio",
            "medidor",
            "evento",
            "lectura",
            "alerta",
            "periodo_facturacion",
        ]:
            cur.execute(f"SELECT COUNT(*) FROM energia.{tabla}")
            con[tabla] = cur.fetchone()[0]

    for tabla, cantidad in con.items():
        print(f"    {tabla:<24} {cantidad:>12,}")

    validacion = config["validation"]
    oks = []
    fallos = []

    if validacion.get("enabled", True):
        if validacion.get("expected_readings") and not (total_lecturas > 200000):
            esperado = validacion["expected_readings"]
            if total_lecturas == esperado:
                oks.append(f"Lecturas exactas: {esperado:,}")
            else:
                fallos.append(f"Lecturas {total_lecturas:,} != esperadas {esperado:,}")
        else:
            oks.append(f"Corrida parcial/demo: {total_lecturas:,} lecturas generadas")

        if validacion.get("minimum_total_records"):
            minimo = validacion["minimum_total_records"]
            total_global = sum(v for k, v in con.items() if k != "lectura") + total_lecturas
            if total_global >= minimo:
                oks.append(f"Registros totales {total_global:,} >= minimo {minimo:,}")
            else:
                fallos.append(f"Registros totales {total_global:,} < minimo {minimo:,}")

    if fallos:
        print("\n    [FALLO] Detalles:")
        for f in fallos:
            print(f"      - {f}")
        return False

    for o in oks:
        print(f"    [OK] {o}")
    print("\n    Validacion final: PASO")
    return True


# ----------------------------------------------------------------------
# Vista previa (muestra de resultados)
# ----------------------------------------------------------------------

def mostrar_muestra(connection, limite=5):
    _separador("MUESTRA DE DATOS")
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.nombre, t.clave, l.ts, l.consumo_kwh, l.consumo_real_kwh
            FROM energia.lectura l
            INNER JOIN energia.medidor m ON m.id_medidor = l.id_medidor
            INNER JOIN energia.servicio s ON s.id_servicio = m.id_servicio
            INNER JOIN energia.tipo_servicio t ON t.id_tipo_servicio = s.id_tipo_servicio
            ORDER BY l.ts, l.id_medidor
            LIMIT %s
            """,
            (limite,),
        )
        filas = cur.fetchall()
    print(f"    {'Servicio':<22} {'Tipo':<14} {'Timestamp':<22} {'kWh':>10} {'Real':>10}")
    for nombre, clave, ts, consumo, real in filas:
        print(
            f"    {nombre:<22} {clave:<14} {str(ts):<22} "
            f"{str(consumo):>10} {str(real):>10}"
        )


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="HyperDataSynthetic - generador HSD")
    parser.add_argument("--servicios", type=int, default=None, help="Numero de servicios")
    parser.add_argument("--dias", type=int, default=None, help="Numero de dias a generar")
    parser.add_argument("--demo", action="store_true", help="Corrida demo 60x90 (2 lotes)")
    parser.add_argument("--reset", action="store_true", help="Borra hechos previos")
    args = parser.parse_args()

    _separador(f"{settings.APP_NAME} - {settings.APP_ENV}")

    config = cargar_yaml(BASE_DIR / "config" / "generation.yaml")
    rules = cargar_yaml(BASE_DIR / "config" / "rules.yaml")

    # Overrides
    if args.demo:
        config["generation"]["services"] = 60
    if args.servicios:
        config["generation"]["services"] = args.servicios
    if args.dias:
        config["generation"]["date_end"] = config["generation"]["date_start"] + timedelta(
            days=args.dias - 1
        )
        config["generation"]["name"] = "hsd_demo_parcial"

    config["generation"]["date_start"] = date.fromisoformat(config["generation"]["date_start"])
    config["generation"]["date_end"] = date.fromisoformat(config["generation"]["date_end"])

    print(
        f"  Escenario: {config['generation']['services']:,} servicios, "
        f"{config['generation']['date_start']} a {config['generation']['date_end']}"
    )
    print(f"  Semilla: {config['generation']['seed']}  batch_size: {config['performance']['batch_size']}")

    # Conexion y checks
    connection = get_connection()
    chequear = check_database(connection, settings.DB_SCHEMA)
    if not chequear["valid"]:
        print("  [FALLO] Faltan tablas del esquema:")
        for t in sorted(chequear["missing"]):
            print(f"    - energia.{t}")
        print("  Aplique primero database/sql/01_esquema.sql y 02_catalogos.sql")
        connection.close()
        sys.exit(1)
    print(f"  Esquema energia.{settings.DB_SCHEMA}: {chequear['found_count']} tablas OK")

    if args.reset:
        limpiar_hechos(connection)

    # Corrida
    id_corrida = crear_corrida(connection, config, hash_params(config))
    print(f"  Corrida registrada: id={id_corrida} ({config['generation']['name']})")

    try:
        # 1. Calendario
        _separador("1. CALENDARIO")
        calendario = generar_calendario(connection, config, rules)
        print(f"    Dias generados: {len(calendario)}")

        # 2. Servicios (lotes)
        _separador("2. SERVICIOS")
        total_servicios = 0
        for lote in generar_servicios(
            connection, config, rules, config["generation"]["services"]
        ):
            copy_lote(
                connection,
                "servicio",
                [
                    "id_servicio", "rpu", "id_zona", "id_tipo_servicio",
                    "id_tarifa", "nombre", "latitud", "longitud",
                    "ocupacion_estimada", "carga_contratada_kw", "tiene_solar",
                ],
                lote,
                etiqueta="Servicios",
            )
            connection.commit()
            total_servicios += len(lote)
        print(f"    Servicios insertados: {total_servicios:,}")

        # 3. Medidores (lotes + reemplazos)
        _separador("3. MEDIDORES")
        total_medidores = 0
        for lote in generar_medidores(
            connection, config, rules,
            n_reemplazos=config["generation"].get("replacement_meters", 0),
        ):
            copy_lote(
                connection,
                "medidor",
                [
                    "id_medidor", "id_servicio", "numero_serie", "marca",
                    "multiplicador", "fecha_instalacion", "fecha_retiro",
                    "calidad_enlace",
                ],
                lote,
                etiqueta="Medidores",
            )
            connection.commit()
            total_medidores += len(lote)
        print(f"    Medidores insertados: {total_medidores:,}")

        # 4. Perfiles (verificacion, los llena 02_catalogos.sql)
        _separador("4. PERFILES HORARIOS")
        verificar_perfiles(connection)

        # 5. Eventos + Alertas + Lecturas (nucleo, lotes de 100,000)
        _separador("5. LECTURAS + EVENTOS + ALERTAS")
        total_lecturas, total_eventos, total_alertas = generar_lecturas(
            connection, config, rules, calendario
        )
        print(f"    Eventos:   {total_eventos:,}")
        print(f"    Alertas:   {total_alertas:,}")
        print(f"    Lecturas:  {total_lecturas:,} (en lotes de {config['performance']['batch_size']:,})")

        # 6. Periodos de facturacion
        _separador("6. PERIODO DE FACTURACION")
        total_periodos = generar_periodos(connection, config)
        print(f"    Periodos:  {total_periodos:,}")

        cerrar_corrida(connection, id_corrida, total_lecturas)

        mostrar_muestra(connection)
        validar(connection, config, total_lecturas)

        _separador("FIN DE LA CORRIDA")
        print(f"  Corrida {id_corrida} completada. Revisa la base energia.{settings.DB_SCHEMA}")

    except Exception as e:
        connection.rollback()
        print(f"\n  [ERROR] Corrida fallida: {e}")
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()