"""
Genera exclusivamente graficas PNG de HyperDataSynthetic.

Caracteristicas:
- No crea, modifica ni exporta archivos CSV.
- Consulta PostgreSQL y agrega los datos dentro de SQL.
- Produce graficas legibles para millones de lecturas.
- Incluye curva horaria de 24 horas con etiquetas AM/PM.
- Incluye mapa de calor por dia de la semana y hora.
- Incluye comparacion real/reportado y desviacion diaria.
- Incluye resumen visual de validaciones.

Ejecucion:
    python Graficas_BD.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

# Permite generar imagenes sin abrir ventanas, incluso en servidores.
matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from database.connection import get_connection


# ======================================================================
# CONFIGURACION
# ======================================================================

BASE_DIR = Path(__file__).resolve().parent
SALIDA = BASE_DIR / "reportes_bd"
SALIDA.mkdir(parents=True, exist_ok=True)

DPI = 180
COLOR_REAL = "#1565C0"
COLOR_REPORTADO = "#EF6C00"
COLOR_PRINCIPAL = "#1976D2"
COLOR_SECUNDARIO = "#42A5F5"
COLOR_ALERTA = "#C62828"
COLOR_OK = "#2E7D32"

# Espacio reservado para que las etiquetas largas no se corten.
plt.rcParams.update(
    {
        "figure.figsize": (12, 6),
        "axes.titlesize": 15,
        "axes.labelsize": 11,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 10,
        "figure.dpi": DPI,
    }
)


# ======================================================================
# UTILIDADES
# ======================================================================


def consultar(connection: Any, consulta_sql: str, parametros=None) -> pd.DataFrame:
    """Ejecuta una consulta y devuelve los resultados como DataFrame."""
    with connection.cursor() as cursor:
        cursor.execute(consulta_sql, parametros)
        if cursor.description is None:
            return pd.DataFrame()
        columnas = [col.name for col in cursor.description]
        filas = cursor.fetchall()
    return pd.DataFrame(filas, columns=columnas)


def validar_datos(df: pd.DataFrame, nombre: str) -> bool:
    """Evita errores y graficas vacias cuando una consulta no devuelve filas."""
    if df.empty:
        print(f"[AVISO] Sin datos para: {nombre}")
        return False
    return True


def guardar(nombre: str) -> None:
    """Guarda la figura actual exclusivamente como PNG."""
    ruta = SALIDA / f"{nombre}.png"
    plt.tight_layout()
    plt.savefig(ruta, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"[OK] Grafica: {ruta}")


def formato_hora_12(hora: int) -> str:
    """Convierte una hora 0-23 en una etiqueta facil de leer AM/PM."""
    hora = int(hora) % 24
    if hora == 0:
        return "12 AM"
    if hora < 12:
        return f"{hora} AM"
    if hora == 12:
        return "12 PM"
    return f"{hora - 12} PM"


def agregar_etiquetas_barras(barras, valores, horizontal=False) -> None:
    """Agrega etiquetas numericas sin notacion cientifica."""
    for barra, valor in zip(barras, valores):
        numero = int(valor)
        if horizontal:
            plt.text(
                barra.get_width(),
                barra.get_y() + barra.get_height() / 2,
                f" {numero:,}",
                va="center",
                ha="left",
                fontsize=8,
            )
        else:
            plt.text(
                barra.get_x() + barra.get_width() / 2,
                barra.get_height(),
                f"{numero:,}",
                va="bottom",
                ha="center",
                fontsize=8,
            )


# ======================================================================
# GRAFICAS GENERALES
# ======================================================================


def grafica_conteos(connection: Any) -> None:
    df = consultar(
        connection,
        """
        SELECT 'Calendario' AS tabla, COUNT(*)::bigint AS registros
        FROM energia.calendario
        UNION ALL SELECT 'Perfiles', COUNT(*) FROM energia.perfil_carga_horaria
        UNION ALL SELECT 'Servicios', COUNT(*) FROM energia.servicio
        UNION ALL SELECT 'Medidores', COUNT(*) FROM energia.medidor
        UNION ALL SELECT 'Eventos', COUNT(*) FROM energia.evento
        UNION ALL SELECT 'Lecturas', COUNT(*) FROM energia.lectura
        UNION ALL SELECT 'Alertas', COUNT(*) FROM energia.alerta
        UNION ALL SELECT 'Facturacion', COUNT(*) FROM energia.periodo_facturacion
        ORDER BY registros DESC
        """,
    )
    if not validar_datos(df, "conteos por tabla"):
        return

    df["registros"] = pd.to_numeric(df["registros"])
    plt.figure(figsize=(12, 6))
    barras = plt.bar(df["tabla"], df["registros"], color=COLOR_PRINCIPAL)
    plt.title("Volumen de registros por tabla")
    plt.xlabel("Tabla")
    plt.ylabel("Registros")
    plt.xticks(rotation=30, ha="right")
    plt.ticklabel_format(style="plain", axis="y")
    plt.grid(axis="y", alpha=0.2)
    agregar_etiquetas_barras(barras, df["registros"])
    guardar("01_conteos_por_tabla")


def grafica_servicios_categoria(connection: Any) -> None:
    df = consultar(
        connection,
        """
        SELECT ts.categoria, COUNT(*)::bigint AS servicios
        FROM energia.servicio s
        JOIN energia.tipo_servicio ts USING (id_tipo_servicio)
        GROUP BY ts.categoria
        ORDER BY servicios DESC
        """,
    )
    if not validar_datos(df, "servicios por categoria"):
        return

    df["servicios"] = pd.to_numeric(df["servicios"])
    plt.figure(figsize=(10, 6))
    barras = plt.bar(df["categoria"], df["servicios"], color=COLOR_SECUNDARIO)
    plt.title("Distribucion de servicios por categoria")
    plt.xlabel("Categoria")
    plt.ylabel("Servicios")
    plt.xticks(rotation=30, ha="right")
    plt.grid(axis="y", alpha=0.2)
    agregar_etiquetas_barras(barras, df["servicios"])
    guardar("02_servicios_por_categoria")


def grafica_top_zonas(connection: Any) -> None:
    df = consultar(
        connection,
        """
        SELECT z.nombre AS zona, COUNT(s.id_servicio)::bigint AS servicios
        FROM energia.zona z
        LEFT JOIN energia.servicio s USING (id_zona)
        GROUP BY z.id_zona, z.nombre
        ORDER BY servicios DESC
        LIMIT 15
        """,
    )
    if not validar_datos(df, "top de zonas"):
        return

    df["servicios"] = pd.to_numeric(df["servicios"])
    df = df.sort_values("servicios")
    plt.figure(figsize=(12, 8))
    barras = plt.barh(df["zona"], df["servicios"], color=COLOR_PRINCIPAL)
    plt.title("Quince zonas con mayor cantidad de servicios")
    plt.xlabel("Servicios")
    plt.ylabel("Zona")
    plt.grid(axis="x", alpha=0.2)
    agregar_etiquetas_barras(barras, df["servicios"], horizontal=True)
    guardar("03_top_15_zonas")


def grafica_eventos_tipo(connection: Any) -> None:
    df = consultar(
        connection,
        """
        SELECT te.nombre AS tipo_evento, COUNT(*)::bigint AS eventos
        FROM energia.evento e
        JOIN energia.tipo_evento te USING (id_tipo_evento)
        GROUP BY te.id_tipo_evento, te.nombre
        ORDER BY eventos DESC
        """,
    )
    if not validar_datos(df, "eventos por tipo"):
        return

    df["eventos"] = pd.to_numeric(df["eventos"])
    df = df.sort_values("eventos")
    plt.figure(figsize=(12, 7))
    barras = plt.barh(df["tipo_evento"], df["eventos"], color="#7E57C2")
    plt.title("Eventos generados por tipo")
    plt.xlabel("Eventos")
    plt.ylabel("Tipo de evento")
    plt.grid(axis="x", alpha=0.2)
    agregar_etiquetas_barras(barras, df["eventos"], horizontal=True)
    guardar("04_eventos_por_tipo")


# ======================================================================
# CONSUMO EN EL TIEMPO
# ======================================================================


def consultar_consumo_diario(connection: Any) -> pd.DataFrame:
    df = consultar(
        connection,
        """
        SELECT
            ts::date AS fecha,
            COUNT(*)::bigint AS lecturas,
            ROUND(SUM(consumo_real_kwh)::numeric, 2) AS consumo_real_kwh,
            ROUND(SUM(COALESCE(consumo_kwh, 0))::numeric, 2) AS consumo_reportado_kwh,
            ROUND(
                SUM(ABS(consumo_real_kwh - COALESCE(consumo_kwh, 0)))::numeric,
                2
            ) AS desviacion_absoluta_kwh
        FROM energia.lectura
        GROUP BY ts::date
        ORDER BY fecha
        """,
    )
    if df.empty:
        return df

    df["fecha"] = pd.to_datetime(df["fecha"])
    for columna in (
        "lecturas",
        "consumo_real_kwh",
        "consumo_reportado_kwh",
        "desviacion_absoluta_kwh",
    ):
        df[columna] = pd.to_numeric(df[columna])
    return df


def grafica_lecturas_diarias(connection: Any) -> None:
    df = consultar_consumo_diario(connection)
    if not validar_datos(df, "lecturas diarias"):
        return

    plt.figure(figsize=(14, 6))
    plt.plot(df["fecha"], df["lecturas"], color=COLOR_PRINCIPAL, linewidth=2)
    plt.fill_between(df["fecha"], df["lecturas"], color=COLOR_SECUNDARIO, alpha=0.25)
    plt.title("Lecturas generadas por dia")
    plt.xlabel("Fecha")
    plt.ylabel("Lecturas")
    plt.ticklabel_format(style="plain", axis="y")
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%d-%b"))
    plt.grid(alpha=0.25)
    guardar("05_lecturas_por_dia")


def grafica_consumo_diario(connection: Any) -> None:
    df = consultar_consumo_diario(connection)
    if not validar_datos(df, "consumo diario"):
        return

    plt.figure(figsize=(14, 6))
    plt.plot(
        df["fecha"],
        df["consumo_real_kwh"],
        label="Consumo real",
        color=COLOR_REAL,
        linewidth=2,
    )
    plt.plot(
        df["fecha"],
        df["consumo_reportado_kwh"],
        label="Consumo reportado",
        color=COLOR_REPORTADO,
        linewidth=1.8,
    )
    plt.title("Consumo real y reportado por dia")
    plt.xlabel("Fecha")
    plt.ylabel("Energia (kWh)")
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%d-%b"))
    plt.grid(alpha=0.25)
    plt.legend()
    guardar("06_consumo_real_vs_reportado_diario")


def grafica_desviacion_diaria(connection: Any) -> None:
    """Muestra en que fechas se concentra la diferencia causada por eventos."""
    df = consultar_consumo_diario(connection)
    if not validar_datos(df, "desviacion diaria"):
        return

    plt.figure(figsize=(14, 6))
    plt.bar(
        df["fecha"],
        df["desviacion_absoluta_kwh"],
        color=COLOR_ALERTA,
        alpha=0.8,
        width=0.8,
    )
    plt.title("Desviacion absoluta entre consumo real y reportado")
    plt.xlabel("Fecha")
    plt.ylabel("Desviacion absoluta (kWh)")
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%d-%b"))
    plt.grid(axis="y", alpha=0.25)
    guardar("07_desviacion_diaria")


# ======================================================================
# CURVAS HORARIAS DE 24 HORAS
# ======================================================================


def grafica_curva_24_horas(connection: Any) -> None:
    """Curva principal con las 24 horas etiquetadas en formato AM/PM."""
    df = consultar(
        connection,
        """
        SELECT
            EXTRACT(HOUR FROM ts)::integer AS hora,
            ROUND(AVG(consumo_real_kwh)::numeric, 4) AS promedio_real_kwh,
            ROUND(AVG(consumo_kwh)::numeric, 4) AS promedio_reportado_kwh
        FROM energia.lectura
        GROUP BY EXTRACT(HOUR FROM ts)
        ORDER BY hora
        """,
    )
    if not validar_datos(df, "curva horaria de 24 horas"):
        return

    for columna in ("hora", "promedio_real_kwh", "promedio_reportado_kwh"):
        df[columna] = pd.to_numeric(df[columna])

    horas = list(range(24))
    etiquetas = [formato_hora_12(hora) for hora in horas]

    plt.figure(figsize=(16, 7))
    plt.plot(
        df["hora"],
        df["promedio_real_kwh"],
        marker="o",
        markersize=5,
        linewidth=2.3,
        color=COLOR_REAL,
        label="Real",
    )
    plt.plot(
        df["hora"],
        df["promedio_reportado_kwh"],
        marker="o",
        markersize=4,
        linewidth=1.8,
        color=COLOR_REPORTADO,
        label="Reportado",
    )
    plt.title("Curva promedio de consumo durante 24 horas")
    plt.xlabel("Hora del dia")
    plt.ylabel("Consumo promedio (kWh)")
    plt.xticks(horas, etiquetas, rotation=55, ha="right")
    plt.xlim(-0.5, 23.5)
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar("08_curva_24_horas_am_pm")


def grafica_curva_categoria_24_horas(connection: Any) -> None:
    df = consultar(
        connection,
        """
        SELECT
            tsrv.categoria,
            EXTRACT(HOUR FROM l.ts)::integer AS hora,
            ROUND(AVG(l.consumo_real_kwh)::numeric, 4) AS consumo_promedio_kwh
        FROM energia.lectura l
        JOIN energia.medidor m USING (id_medidor)
        JOIN energia.servicio s USING (id_servicio)
        JOIN energia.tipo_servicio tsrv USING (id_tipo_servicio)
        GROUP BY tsrv.categoria, EXTRACT(HOUR FROM l.ts)
        ORDER BY tsrv.categoria, hora
        """,
    )
    if not validar_datos(df, "curva horaria por categoria"):
        return

    df["hora"] = pd.to_numeric(df["hora"])
    df["consumo_promedio_kwh"] = pd.to_numeric(df["consumo_promedio_kwh"])
    horas = list(range(24))
    etiquetas = [formato_hora_12(hora) for hora in horas]

    plt.figure(figsize=(16, 8))
    for categoria, grupo in df.groupby("categoria"):
        plt.plot(
            grupo["hora"],
            grupo["consumo_promedio_kwh"],
            marker="o",
            markersize=3.5,
            linewidth=1.8,
            label=categoria,
        )

    plt.title("Curva de consumo de 24 horas por categoria")
    plt.xlabel("Hora del dia")
    plt.ylabel("Consumo promedio real (kWh)")
    plt.xticks(horas, etiquetas, rotation=55, ha="right")
    plt.xlim(-0.5, 23.5)
    plt.grid(True, alpha=0.25)
    plt.legend(ncol=2)
    guardar("09_curva_categoria_24_horas")


def grafica_mapa_calor(connection: Any) -> None:
    """Mapa de calor agregado, adecuado para millones de lecturas."""
    df = consultar(
        connection,
        """
        SELECT
            EXTRACT(ISODOW FROM l.ts)::integer AS dia_semana,
            EXTRACT(HOUR FROM l.ts)::integer AS hora,
            ROUND(AVG(l.consumo_real_kwh)::numeric, 4) AS promedio_kwh
        FROM energia.lectura l
        GROUP BY
            EXTRACT(ISODOW FROM l.ts),
            EXTRACT(HOUR FROM l.ts)
        ORDER BY dia_semana, hora
        """,
    )
    if not validar_datos(df, "mapa de calor"):
        return

    df["promedio_kwh"] = pd.to_numeric(df["promedio_kwh"])
    matriz = (
        df.pivot(index="dia_semana", columns="hora", values="promedio_kwh")
        .reindex(index=range(1, 8), columns=range(24))
        .fillna(0.0)
    )

    dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
    etiquetas_hora = [formato_hora_12(hora) for hora in range(24)]

    plt.figure(figsize=(17, 6))
    imagen = plt.imshow(matriz.values, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    plt.title("Mapa de calor del consumo promedio por dia y hora")
    plt.xlabel("Hora del dia")
    plt.ylabel("Dia de la semana")
    plt.xticks(range(24), etiquetas_hora, rotation=55, ha="right")
    plt.yticks(range(7), dias)
    barra = plt.colorbar(imagen)
    barra.set_label("Consumo promedio real (kWh)")
    guardar("10_mapa_calor_dia_hora")


# ======================================================================
# MEDIDORES Y ALERTAS
# ======================================================================


def grafica_marcas_medidores(connection: Any) -> None:
    """Comprueba visualmente la distribucion configurada de marcas."""
    df = consultar(
        connection,
        """
        SELECT COALESCE(marca, 'SIN MARCA') AS marca,
               COUNT(*)::bigint AS medidores
        FROM energia.medidor
        GROUP BY COALESCE(marca, 'SIN MARCA')
        ORDER BY medidores DESC
        """,
    )
    if not validar_datos(df, "marcas de medidores"):
        return

    df["medidores"] = pd.to_numeric(df["medidores"])
    plt.figure(figsize=(10, 6))
    barras = plt.bar(df["marca"], df["medidores"], color="#00897B")
    plt.title("Distribucion de marcas de medidores")
    plt.xlabel("Marca")
    plt.ylabel("Medidores")
    plt.grid(axis="y", alpha=0.2)
    agregar_etiquetas_barras(barras, df["medidores"])
    guardar("11_marcas_medidores")


def grafica_alertas_prioridad(connection: Any) -> None:
    df = consultar(
        connection,
        """
        SELECT prioridad, COUNT(*)::bigint AS alertas
        FROM energia.alerta
        GROUP BY prioridad
        ORDER BY prioridad
        """,
    )
    if not validar_datos(df, "alertas por prioridad"):
        return

    df["prioridad"] = df["prioridad"].astype(str)
    df["alertas"] = pd.to_numeric(df["alertas"])
    plt.figure(figsize=(9, 6))
    barras = plt.bar(df["prioridad"], df["alertas"], color="#D84315")
    plt.title("Alertas por prioridad")
    plt.xlabel("Prioridad")
    plt.ylabel("Alertas")
    plt.grid(axis="y", alpha=0.2)
    agregar_etiquetas_barras(barras, df["alertas"])
    guardar("12_alertas_por_prioridad")


# ======================================================================
# VALIDACIONES VISUALES
# ======================================================================


def grafica_validaciones(connection: Any) -> None:
    """Genera una imagen de validaciones; no crea archivos tabulares."""
    df = consultar(
        connection,
        """
        SELECT 'Medidores sin servicio' AS validacion, COUNT(*)::bigint AS inconsistencias
        FROM energia.medidor m
        LEFT JOIN energia.servicio s USING (id_servicio)
        WHERE s.id_servicio IS NULL

        UNION ALL
        SELECT 'Eventos sin medidor', COUNT(*)
        FROM energia.evento e
        LEFT JOIN energia.medidor m USING (id_medidor)
        WHERE m.id_medidor IS NULL

        UNION ALL
        SELECT 'Lecturas sin medidor', COUNT(*)
        FROM energia.lectura l
        LEFT JOIN energia.medidor m USING (id_medidor)
        WHERE m.id_medidor IS NULL

        UNION ALL
        SELECT 'Eventos con fechas invalidas', COUNT(*)
        FROM energia.evento
        WHERE ts_fin <= ts_inicio

        UNION ALL
        SELECT 'Lecturas reales negativas', COUNT(*)
        FROM energia.lectura
        WHERE consumo_real_kwh < 0

        UNION ALL
        SELECT 'Lecturas reales nulas', COUNT(*)
        FROM energia.lectura
        WHERE consumo_real_kwh IS NULL

        UNION ALL
        SELECT 'Calidad de enlace invalida', COUNT(*)
        FROM energia.medidor
        WHERE calidad_enlace IS NULL
           OR calidad_enlace < 0
           OR calidad_enlace > 100

        ORDER BY validacion
        """,
    )
    if not validar_datos(df, "validaciones"):
        return

    df["inconsistencias"] = pd.to_numeric(df["inconsistencias"])
    df = df.sort_values("inconsistencias")
    colores = [COLOR_OK if valor == 0 else COLOR_ALERTA for valor in df["inconsistencias"]]

    plt.figure(figsize=(13, 7))
    barras = plt.barh(df["validacion"], df["inconsistencias"], color=colores)
    plt.title("Resumen de validaciones de integridad")
    plt.xlabel("Inconsistencias detectadas")
    plt.ylabel("Validacion")
    plt.grid(axis="x", alpha=0.2)
    agregar_etiquetas_barras(barras, df["inconsistencias"], horizontal=True)
    guardar("13_validaciones_integridad")

    total = int(df["inconsistencias"].sum())
    if total == 0:
        print("[OK] Las validaciones no detectaron inconsistencias")
    else:
        print(f"[ADVERTENCIA] Se detectaron {total:,} inconsistencias")


# ======================================================================
# EJECUCION
# ======================================================================


def main() -> int:
    print("=" * 72)
    print("ANALISIS VISUAL DE HYPERDATASYNTHETIC")
    print("=" * 72)
    print("Salida exclusiva de imagenes PNG")
    print(f"Carpeta de salida: {SALIDA}")

    connection = get_connection()
    if connection is None:
        raise ConnectionError("No fue posible obtener una conexion PostgreSQL")

    try:
        grafica_conteos(connection)
        grafica_servicios_categoria(connection)
        grafica_top_zonas(connection)
        grafica_eventos_tipo(connection)
        grafica_lecturas_diarias(connection)
        grafica_consumo_diario(connection)
        grafica_desviacion_diaria(connection)
        grafica_curva_24_horas(connection)
        grafica_curva_categoria_24_horas(connection)
        grafica_mapa_calor(connection)
        grafica_marcas_medidores(connection)
        grafica_alertas_prioridad(connection)
        grafica_validaciones(connection)

        print()
        print("[OK] Analisis visual terminado")
        print(f"[OK] Imagenes guardadas en: {SALIDA}")
        return 0
    finally:
        connection.close()
        print("[OK] Conexion PostgreSQL cerrada")


if __name__ == "__main__":
    raise SystemExit(main())
