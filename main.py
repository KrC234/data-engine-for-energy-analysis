"""
HYPERDATASYNTHETIC - ORQUESTADOR PRINCIPAL
main.py

Version mejorada para el proyecto de Ramiro.

Incorpora:
- Argumentos --demo, --servicios, --dias y --reset.
- Registro de corridas en energia.corrida_generacion.
- Hash SHA-256 del contenido completo de generation.yaml y rules.yaml.
- Validacion posterior consultando PostgreSQL.
- Muestra final de lecturas.
- Soporte para COPY desde el orquestador cuando un generador devuelve lotes.
- Flujo explicito y ordenado de los generadores.
- Registro de inicio, fin, estado y total de lecturas.

Compatibilidad:
- Los generadores actuales pueden insertar internamente y devolver un entero.
- Los generadores futuros pueden devolver lotes para que main.py use COPY.
- Acepta nombres de configuracion en ingles y espanol.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

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
# RUTAS
# ======================================================================

BASE_DIR = Path(__file__).resolve().parent
GENERATION_YAML = BASE_DIR / "config" / "generation.yaml"
RULES_YAML = BASE_DIR / "config" / "rules.yaml"


# ======================================================================
# DEFINICION DE ETAPAS
# ======================================================================

@dataclass(frozen=True)
class Etapa:
    nombre: str
    generador: Callable[..., Any]
    tabla_copy: str | None = None
    columnas_copy: tuple[str, ...] = ()


ETAPAS = (
    Etapa("Calendario", generar_calendario),
    Etapa("Perfiles", generar_perfiles),
    Etapa(
        "Servicios",
        generar_servicios,
        "servicio",
        (
            "id_servicio",
            "rpu",
            "id_zona",
            "id_tipo_servicio",
            "id_tarifa",
            "nombre",
            "latitud",
            "longitud",
            "ocupacion_estimada",
            "carga_contratada_kw",
            "tiene_solar",
        ),
    ),
    Etapa(
        "Dispositivos",
        generar_dispositivos,
        "medidor",
        (
            "id_medidor",
            "id_servicio",
            "numero_serie",
            "marca",
            "multiplicador",
            "fecha_instalacion",
            "fecha_retiro",
            "calidad_enlace",
        ),
    ),
    Etapa("Eventos", generar_eventos),
    Etapa("Lecturas", generar_lecturas),
    Etapa("Alertas", generar_alertas),
    Etapa("Facturacion", generar_facturacion),
)


TABLAS_VALIDACION = (
    "calendario",
    "perfil_carga_horaria",
    "servicio",
    "medidor",
    "evento",
    "lectura",
    "alerta",
    "periodo_facturacion",
)

TABLAS_RESET = (
    "alerta",
    "periodo_facturacion",
    "lectura",
    "evento",
    "medidor",
    "servicio",
    "calendario",
    "corrida_generacion",
)


# ======================================================================
# UTILIDADES GENERALES
# ======================================================================

def separador(titulo: str, ancho: int = 72) -> None:
    print()
    print("=" * ancho)
    print(titulo)
    print("=" * ancho)


def cargar_yaml(ruta: Path) -> dict[str, Any]:
    """Carga y valida un archivo YAML."""
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontro el archivo: {ruta}")
    if not ruta.is_file():
        raise FileNotFoundError(f"La ruta no es un archivo: {ruta}")

    try:
        with ruta.open("r", encoding="utf-8") as archivo:
            contenido = yaml.safe_load(archivo)
    except yaml.YAMLError as error:
        raise ValueError(
            f"El archivo YAML contiene un error: {ruta}\nDetalle: {error}"
        ) from error

    if contenido is None:
        raise ValueError(f"El archivo YAML esta vacio: {ruta}")
    if not isinstance(contenido, dict):
        raise ValueError(f"El contenido principal debe ser un diccionario: {ruta}")

    return contenido


def cargar_configuracion() -> tuple[dict[str, Any], dict[str, Any]]:
    print("Cargando configuracion...")
    config = cargar_yaml(GENERATION_YAML)
    rules = cargar_yaml(RULES_YAML)
    print("[OK] generation.yaml")
    print("[OK] rules.yaml")
    return config, rules


def seccion_generacion(config: dict[str, Any]) -> dict[str, Any]:
    generation = config.get("generation")
    return generation if isinstance(generation, dict) else config


def obtener(config: dict[str, Any], nombres: Iterable[str], default: Any = None) -> Any:
    for nombre in nombres:
        if nombre in config and config[nombre] is not None:
            return config[nombre]
    return default


def convertir_fecha(valor: Any, nombre: str) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{nombre} debe usar formato YYYY-MM-DD: {valor!r}") from error


def normalizar_configuracion(config: dict[str, Any]) -> dict[str, Any]:
    """Normaliza fechas y nombres comunes sin eliminar las claves originales."""
    generation = seccion_generacion(config)

    inicio = obtener(
        generation,
        ("start_date", "date_start", "fecha_inicial", "fecha_inicio", "fecha_desde"),
    )
    fin = obtener(
        generation,
        ("end_date", "date_end", "fecha_final", "fecha_fin", "fecha_hasta"),
    )

    if inicio is None or fin is None:
        raise KeyError("Faltan las fechas inicial y final en generation.yaml")

    fecha_inicio = convertir_fecha(inicio, "fecha inicial")
    fecha_fin = convertir_fecha(fin, "fecha final")
    if fecha_fin < fecha_inicio:
        raise ValueError("La fecha final no puede ser anterior a la fecha inicial")

    # Claves canonicas usadas por los generadores de Ramiro.
    generation["start_date"] = fecha_inicio
    generation["end_date"] = fecha_fin

    # Alias para compatibilidad con generadores que usan la convencion de Mateo.
    generation["date_start"] = fecha_inicio
    generation["date_end"] = fecha_fin

    intervalo = obtener(
        generation,
        ("reading_interval_minutes", "interval_minutes", "intervalo_min", "intervalo_minutos"),
        60,
    )
    generation["reading_interval_minutes"] = int(intervalo)
    generation["interval_minutes"] = int(intervalo)

    return config


def serializar_hash(valor: Any) -> str:
    """Serializa fechas y otras estructuras de manera estable."""
    def default(obj: Any) -> str:
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return str(obj)

    return json.dumps(valor, default=default, sort_keys=True, ensure_ascii=False)


def calcular_hash(config: dict[str, Any], rules: dict[str, Any]) -> str:
    """Calcula SHA-256 usando el contenido completo de ambos YAML."""
    texto = serializar_hash({"generation": config, "rules": rules})
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def mostrar_configuracion(config: dict[str, Any], hash_config: str) -> None:
    generation = seccion_generacion(config)
    separador("CONFIGURACION DE LA CORRIDA")
    print(f"Nombre ............... {obtener(generation, ('name', 'nombre'), 'Corrida sin nombre')}")
    print(f"Semilla .............. {obtener(generation, ('seed', 'semilla'), 'No definida')}")
    print(f"Fecha inicial ........ {generation['start_date']}")
    print(f"Fecha final .......... {generation['end_date']}")
    print(f"Intervalo ............ {generation['reading_interval_minutes']} minutos")
    print(
        "Servicios ............ "
        f"{obtener(generation, ('services', 'service_count', 'numero_servicios', 'total_servicios'), 'No definido')}"
    )
    performance = config.get("performance", {})
    print(f"Tamano de lote ....... {performance.get('batch_size', generation.get('batch_size', 'No definido'))}")
    print(f"Hash ................. {hash_config}")


# ======================================================================
# ARGUMENTOS DE TERMINAL
# ======================================================================

def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HyperDataSynthetic - orquestador de generacion de Ramiro"
    )
    parser.add_argument("--servicios", type=int, default=None, help="Cantidad de servicios")
    parser.add_argument("--dias", type=int, default=None, help="Cantidad de dias inclusivos")
    parser.add_argument("--demo", action="store_true", help="Ejecuta una corrida demo")
    parser.add_argument("--reset", action="store_true", help="Limpia tablas de hechos")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Confirma operaciones destructivas como --reset",
    )
    parser.add_argument(
        "--solo",
        choices=[etapa.nombre for etapa in ETAPAS],
        help="Ejecuta solamente una etapa",
    )
    parser.add_argument(
        "--sin-muestra",
        action="store_true",
        help="No muestra lecturas al finalizar",
    )
    return parser


def aplicar_argumentos(config: dict[str, Any], args: argparse.Namespace) -> None:
    generation = seccion_generacion(config)

    if args.demo:
        generation["services"] = 60
        generation["name"] = "hsd_demo_ramiro"

    if args.servicios is not None:
        if args.servicios <= 0:
            raise ValueError("--servicios debe ser mayor que cero")
        generation["services"] = args.servicios

    if args.dias is not None:
        if args.dias <= 0:
            raise ValueError("--dias debe ser mayor que cero")
        fecha_inicio = convertir_fecha(generation["start_date"], "fecha inicial")
        fecha_fin = fecha_inicio + timedelta(days=args.dias - 1)
        generation["end_date"] = fecha_fin
        generation["date_end"] = fecha_fin
        generation["name"] = "hsd_corrida_parcial_ramiro"


# ======================================================================
# METADATOS DE BASE DE DATOS
# ======================================================================

def tabla_existe(connection: Any, esquema: str, tabla: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            )
            """,
            (esquema, tabla),
        )
        return bool(cursor.fetchone()[0])


def columnas_tabla(connection: Any, esquema: str, tabla: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (esquema, tabla),
        )
        return {fila[0] for fila in cursor.fetchall()}


def validar_base_datos(connection: Any) -> None:
    """Ejecuta check_database respetando firmas comunes."""
    firma = inspect.signature(check_database)
    cantidad = len(firma.parameters)

    if cantidad == 0:
        resultado = check_database()
    elif cantidad == 1:
        resultado = check_database(connection)
    else:
        resultado = check_database(connection, "energia")

    if isinstance(resultado, dict) and not resultado.get("valid", True):
        faltantes = resultado.get("missing", [])
        raise RuntimeError(
            "La base de datos no esta preparada. Faltan: " + ", ".join(map(str, faltantes))
        )
    if resultado is False:
        raise RuntimeError("La validacion de la base de datos no fue superada")


# ======================================================================
# REGISTRO DE CORRIDAS
# ======================================================================

def crear_corrida(
    connection: Any,
    config: dict[str, Any],
    hash_config: str,
) -> int | None:
    """Registra el inicio de la corrida si la tabla existe."""
    tabla = "corrida_generacion"
    if not tabla_existe(connection, "energia", tabla):
        print("[AVISO] energia.corrida_generacion no existe; se omite trazabilidad")
        return None

    columnas = columnas_tabla(connection, "energia", tabla)
    generation = seccion_generacion(config)

    valores_disponibles = {
        "nombre": str(obtener(generation, ("name", "nombre"), "Corrida Ramiro"))[:100],
        "semilla": int(obtener(generation, ("seed", "semilla"), 42)),
        "version_reglas": str(generation.get("rules_version", "sin_version"))[:50],
        "hash_parametros": hash_config,
        "ts_inicio_ejecucion": datetime.now(),
        "fecha_desde": generation["start_date"],
        "fecha_hasta": generation["end_date"],
        "intervalo_min": generation["reading_interval_minutes"],
        "estado": "EN_PROCESO",
        "total_lecturas": 0,
    }

    campos = [campo for campo in valores_disponibles if campo in columnas]
    valores = [valores_disponibles[campo] for campo in campos]

    with connection.cursor() as cursor:
        if "id_corrida" in columnas:
            cursor.execute(
                "SELECT COALESCE(MAX(id_corrida), 0) + 1 FROM energia.corrida_generacion"
            )
            id_corrida = int(cursor.fetchone()[0])
            campos.insert(0, "id_corrida")
            valores.insert(0, id_corrida)
        else:
            id_corrida = None

        nombres = ", ".join(campos)
        marcadores = ", ".join(["%s"] * len(campos))
        retorno = " RETURNING id_corrida" if "id_corrida" in columnas and id_corrida is None else ""
        cursor.execute(
            f"INSERT INTO energia.corrida_generacion ({nombres}) VALUES ({marcadores}){retorno}",
            tuple(valores),
        )
        if retorno:
            id_corrida = int(cursor.fetchone()[0])

    connection.commit()
    print(f"[OK] Corrida registrada: {id_corrida if id_corrida is not None else 'sin id'}")
    return id_corrida


def cerrar_corrida(
    connection: Any,
    id_corrida: int | None,
    estado: str,
    total_lecturas: int,
    mensaje_error: str | None = None,
) -> None:
    if id_corrida is None or not tabla_existe(connection, "energia", "corrida_generacion"):
        return

    columnas = columnas_tabla(connection, "energia", "corrida_generacion")
    asignaciones = []
    valores = []

    candidatos = {
        "ts_fin_ejecucion": datetime.now(),
        "total_lecturas": total_lecturas,
        "estado": estado,
        "mensaje_error": mensaje_error,
        "error": mensaje_error,
    }

    for campo, valor in candidatos.items():
        if campo in columnas and not (campo == "error" and "mensaje_error" in columnas):
            asignaciones.append(f"{campo} = %s")
            valores.append(valor)

    if not asignaciones:
        return

    valores.append(id_corrida)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE energia.corrida_generacion SET "
            + ", ".join(asignaciones)
            + " WHERE id_corrida = %s",
            tuple(valores),
        )
    connection.commit()


# ======================================================================
# RESET SEGURO
# ======================================================================

def limpiar_hechos(connection: Any, force: bool) -> None:
    """
    Elimina los datos generados y conserva los catalogos.

    CONTINUE IDENTITY evita reiniciar secuencias porque el usuario
    de la aplicacion puede no ser propietario de todas ellas.
    """
    if not force:
        raise RuntimeError(
            "--reset requiere tambien --force por seguridad"
        )

    separador("RESET DE DATOS")

    tablas_existentes = [
        tabla
        for tabla in TABLAS_RESET
        if tabla_existe(connection, "energia", tabla)
    ]

    if not tablas_existentes:
        print("[AVISO] No se encontraron tablas para limpiar.")
        return

    tablas_sql = ", ".join(
        f"energia.{tabla}"
        for tabla in tablas_existentes
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                TRUNCATE TABLE
                    {tablas_sql}
                CONTINUE IDENTITY CASCADE
                """
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    for tabla in tablas_existentes:
        print(f"[OK] energia.{tabla} limpiada")

    print()
    print("[OK] Reset completado correctamente")
    print("[INFO] Las secuencias conservaron su valor actual")
    print("[INFO] Los catalogos no fueron eliminados")

# ======================================================================
# COPY DESDE EL ORQUESTADOR
# ======================================================================

def es_iterador_de_lotes(resultado: Any) -> bool:
    if resultado is None or isinstance(resultado, (str, bytes, dict, int, float, bool, list, tuple)):
        return False
    return hasattr(resultado, "__iter__")


def copiar_lote_orquestador(
    connection: Any,
    tabla: str,
    columnas: tuple[str, ...],
    lote: list[tuple[Any, ...]] | list[list[Any]],
) -> int:
    """Inserta un lote mediante Psycopg 3 COPY FROM STDIN."""
    if not lote:
        return 0

    nombres = ", ".join(columnas)
    consulta = f"COPY energia.{tabla} ({nombres}) FROM STDIN"

    with connection.cursor() as cursor:
        with cursor.copy(consulta) as copy:
            for fila in lote:
                copy.write_row(tuple(fila))

    return len(lote)


def consumir_lotes(
    connection: Any,
    etapa: Etapa,
    resultado: Iterator[Any],
) -> int:
    if not etapa.tabla_copy or not etapa.columnas_copy:
        raise RuntimeError(
            f"{etapa.nombre} devolvio lotes, pero la etapa no define tabla/columnas COPY"
        )

    total = 0
    for numero, lote in enumerate(resultado, start=1):
        if not isinstance(lote, (list, tuple)):
            raise TypeError(f"El lote {numero} de {etapa.nombre} no es una lista o tupla")
        insertados = copiar_lote_orquestador(
            connection,
            etapa.tabla_copy,
            etapa.columnas_copy,
            list(lote),
        )
        connection.commit()
        total += insertados
        print(f"[COPY {numero:03d}] {etapa.nombre}: {total:,} registros")

    return total


# ======================================================================
# EJECUCION EXPLICITA DE ETAPAS
# ======================================================================

def invocar_generador(
    generador: Callable[..., Any],
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> Any:
    """Invoca generadores con el contrato uniforme de Ramiro."""
    return generador(connection=connection, config=config, rules=rules)


def ejecutar_etapa(
    connection: Any,
    etapa: Etapa,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    inicio = time.perf_counter()
    resultado = invocar_generador(etapa.generador, connection, config, rules)

    if es_iterador_de_lotes(resultado):
        registros = consumir_lotes(connection, etapa, resultado)
    elif isinstance(resultado, int) and not isinstance(resultado, bool):
        registros = resultado
    elif isinstance(resultado, tuple) and all(
        isinstance(valor, int) and not isinstance(valor, bool) for valor in resultado
    ):
        registros = resultado
    elif isinstance(resultado, (list, tuple, dict, set)):
        registros = len(resultado)
    else:
        registros = None

    duracion = time.perf_counter() - inicio
    return {
        "nombre": etapa.nombre,
        "estado": "COMPLETADO",
        "registros": registros,
        "duracion": duracion,
        "resultado_original": resultado,
    }


def ejecutar_flujo(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
    solo: str | None,
) -> list[dict[str, Any]]:
    etapas = [etapa for etapa in ETAPAS if solo is None or etapa.nombre == solo]
    resultados = []

    separador("GENERACION DE DATOS")
    for numero, etapa in enumerate(etapas, start=1):
        print()
        print("-" * 72)
        print(f"[{numero}/{len(etapas)}] {etapa.nombre}")
        print("-" * 72)

        try:
            resultado = ejecutar_etapa(connection, etapa, config, rules)
            resultados.append(resultado)
            detalle = resultado["registros"]
            if isinstance(detalle, int):
                texto = f"{detalle:,} registros"
            elif isinstance(detalle, tuple):
                texto = ", ".join(f"{valor:,}" for valor in detalle)
            else:
                texto = "completado"
            print(f"[OK] {etapa.nombre}: {texto} en {resultado['duracion']:.2f} s")
        except Exception as error:
            resultados.append(
                {
                    "nombre": etapa.nombre,
                    "estado": "ERROR",
                    "registros": None,
                    "duracion": 0.0,
                    "error": str(error),
                }
            )
            print(f"[ERROR] Fallo la etapa {etapa.nombre}")
            print(f"Tipo: {type(error).__name__}")
            print(f"Detalle: {error}")
            raise

    return resultados


# ======================================================================
# VALIDACION Y MUESTRA FINAL
# ======================================================================

def contar_tablas(connection: Any) -> dict[str, int]:
    conteos = {}
    with connection.cursor() as cursor:
        for tabla in TABLAS_VALIDACION:
            if not tabla_existe(connection, "energia", tabla):
                continue
            cursor.execute(f"SELECT COUNT(*) FROM energia.{tabla}")
            conteos[tabla] = int(cursor.fetchone()[0])
    return conteos


def calcular_lecturas_esperadas(connection: Any, config: dict[str, Any]) -> int | None:
    """Calcula lecturas esperadas respetando instalacion y retiro."""
    if not tabla_existe(connection, "energia", "medidor"):
        return None

    generation = seccion_generacion(config)
    inicio = generation["start_date"]
    fin = generation["end_date"]
    intervalo = int(generation["reading_interval_minutes"])
    slots_dia = (24 * 60) // intervalo

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT fecha_instalacion, fecha_retiro
            FROM energia.medidor
            """
        )
        filas = cursor.fetchall()

    total = 0
    for instalacion, retiro in filas:
        if isinstance(instalacion, datetime):
            instalacion = instalacion.date()
        if isinstance(retiro, datetime):
            retiro = retiro.date()
        desde = max(inicio, instalacion or inicio)
        hasta_exclusivo = min(fin + timedelta(days=1), retiro or (fin + timedelta(days=1)))
        dias = max((hasta_exclusivo - desde).days, 0)
        total += dias * slots_dia
    return total


def validar_resultado(
    connection: Any,
    config: dict[str, Any],
    solo: str | None = None,
) -> tuple[bool, dict[str, int]]:
    separador("VALIDACION FINAL")
    conteos = contar_tablas(connection)
    for tabla, cantidad in conteos.items():
        print(f"{tabla:.<32} {cantidad:>15,}")

    fallos = []
    generation = seccion_generacion(config)
    servicios_config = obtener(
        generation,
        ("services", "service_count", "numero_servicios", "total_servicios"),
    )

    if solo is None and servicios_config is not None and "servicio" in conteos:
        if conteos["servicio"] != int(servicios_config):
            fallos.append(
                f"Servicios en BD {conteos['servicio']:,} != configurados {int(servicios_config):,}"
            )

    if solo is None and "servicio" in conteos and "medidor" in conteos:
        if conteos["medidor"] < conteos["servicio"]:
            fallos.append("Hay menos medidores que servicios")

    if solo is None and "lectura" in conteos:
        esperado = calcular_lecturas_esperadas(connection, config)
        if esperado is not None:
            if conteos["lectura"] != esperado:
                fallos.append(
                    f"Lecturas en BD {conteos['lectura']:,} != esperadas {esperado:,}"
                )
            else:
                print(f"[OK] Lecturas esperadas: {esperado:,}")

    if solo in (None, "Perfiles") and tabla_existe(connection, "energia", "perfil_carga_horaria"):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT id_tipo_servicio, tipo_dia
                    FROM energia.perfil_carga_horaria
                    GROUP BY id_tipo_servicio, tipo_dia
                    HAVING COUNT(*) <> 24
                       OR ABS(SUM(factor) - 24.0) > 0.01
                       OR MIN(factor) < 0
                       OR MAX(factor) > 6
                ) AS problemas
                """
            )
            perfiles_invalidos = int(cursor.fetchone()[0])
        if perfiles_invalidos:
            fallos.append(f"Existen {perfiles_invalidos} curvas de perfil invalidas")
        else:
            print("[OK] Perfiles horarios completos y normalizados")

    if fallos:
        print("\n[FALLO] La validacion final encontro problemas:")
        for fallo in fallos:
            print(f"  - {fallo}")
        return False, conteos

    print("\n[OK] VALIDACION FINAL SUPERADA")
    return True, conteos


def mostrar_muestra(connection: Any, limite: int = 5) -> None:
    if not tabla_existe(connection, "energia", "lectura"):
        return

    separador("MUESTRA FINAL DE LECTURAS")
    consulta = """
        SELECT
            s.id_servicio,
            s.nombre,
            m.numero_serie,
            l.ts,
            l.consumo_kwh,
            l.consumo_real_kwh,
            l.id_evento
        FROM energia.lectura l
        INNER JOIN energia.medidor m
            ON m.id_medidor = l.id_medidor
        INNER JOIN energia.servicio s
            ON s.id_servicio = m.id_servicio
        ORDER BY l.ts, l.id_medidor
        LIMIT %s
    """

    with connection.cursor() as cursor:
        cursor.execute(consulta, (limite,))
        filas = cursor.fetchall()

    if not filas:
        print("No hay lecturas para mostrar.")
        return

    for id_servicio, nombre, serie, ts, consumo, real, id_evento in filas:
        print(
            f"Servicio {id_servicio} | {str(nombre)[:25]} | {serie} | {ts} | "
            f"reportado={consumo} | real={real} | evento={id_evento}"
        )


def mostrar_resumen(resultados: list[dict[str, Any]], duracion_total: float) -> None:
    separador("RESUMEN DE LA GENERACION")
    for resultado in resultados:
        nombre = resultado["nombre"]
        estado = resultado["estado"]
        registros = resultado.get("registros")
        duracion = resultado.get("duracion", 0.0)
        if isinstance(registros, int):
            detalle = f"{registros:,} registros"
        elif isinstance(registros, tuple):
            detalle = ", ".join(f"{valor:,}" for valor in registros)
        else:
            detalle = estado
        print(f"[{estado}] {nombre:.<25} {detalle:>20} | {duracion:>8.2f} s")
    print(f"\nTiempo total: {duracion_total:.2f} segundos")


def total_lecturas_desde_resultados(
    resultados: list[dict[str, Any]],
    conteos: dict[str, int] | None = None,
) -> int:
    if conteos and "lectura" in conteos:
        return conteos["lectura"]
    for resultado in resultados:
        if resultado["nombre"] == "Lecturas":
            registros = resultado.get("registros")
            if isinstance(registros, int):
                return registros
            if isinstance(registros, tuple) and registros:
                return int(registros[0])
    return 0


# ======================================================================
# MAIN
# ======================================================================

def main(argv: list[str] | None = None) -> int:
    parser = crear_parser()
    args = parser.parse_args(argv)

    connection = None
    id_corrida = None
    resultados: list[dict[str, Any]] = []
    conteos: dict[str, int] = {}
    inicio_total = time.perf_counter()

    separador("HYPERDATASYNTHETIC - RAMIRO VEGA MEZA")

    try:
        config, rules = cargar_configuracion()
        config = normalizar_configuracion(config)
        aplicar_argumentos(config, args)
        hash_config = calcular_hash(config, rules)
        mostrar_configuracion(config, hash_config)

        print("\nConectando con PostgreSQL...")
        connection = get_connection()
        if connection is None:
            raise ConnectionError("get_connection() no devolvio una conexion valida")
        print("[OK] Conexion establecida")

        print("\nVerificando base de datos...")
        validar_base_datos(connection)
        print("[OK] Base de datos preparada")

        if args.reset:
            limpiar_hechos(connection, args.force)

        id_corrida = crear_corrida(connection, config, hash_config)
        resultados = ejecutar_flujo(connection, config, rules, args.solo)

        # Los generadores pueden manejar lotes, pero se confirma cualquier
        # transaccion pendiente antes de validar.
        connection.commit()

        validacion_ok, conteos = validar_resultado(connection, config, args.solo)
        if not validacion_ok:
            raise RuntimeError("La validacion final de la corrida no fue superada")

        if not args.sin_muestra:
            mostrar_muestra(connection)

        total_lecturas = total_lecturas_desde_resultados(resultados, conteos)
        cerrar_corrida(
            connection,
            id_corrida,
            estado="COMPLETADA",
            total_lecturas=total_lecturas,
        )

        duracion_total = time.perf_counter() - inicio_total
        mostrar_resumen(resultados, duracion_total)
        separador("[OK] GENERACION FINALIZADA")
        return 0

    except KeyboardInterrupt:
        if connection is not None:
            connection.rollback()
            cerrar_corrida(connection, id_corrida, "CANCELADA", 0, "Cancelada por usuario")
        print("\n[CANCELADO] Generacion cancelada por el usuario")
        return 130

    except Exception as error:
        if connection is not None:
            try:
                connection.rollback()
                total_lecturas = total_lecturas_desde_resultados(resultados, conteos)
                cerrar_corrida(
                    connection,
                    id_corrida,
                    estado="ERROR",
                    total_lecturas=total_lecturas,
                    mensaje_error=f"{type(error).__name__}: {error}",
                )
            except Exception as cierre_error:
                print(f"[ADVERTENCIA] No fue posible cerrar la corrida: {cierre_error}")

        separador("[ERROR] GENERACION INTERRUMPIDA")
        print(f"Tipo: {type(error).__name__}")
        print(f"Detalle: {error}")
        return 1

    finally:
        if connection is not None:
            try:
                connection.close()
                print("\n[OK] Conexion PostgreSQL cerrada")
            except Exception as error:
                print(f"[ADVERTENCIA] No fue posible cerrar la conexion: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
