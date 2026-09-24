"""
Grafica el consumo de un dia completo usando reloj de 12 horas con AM/PM.

Ejecutar desde la raiz del proyecto:
    python grafica_consumo_12h_ampm.py

Salidas:
    reportes_bd/consumo_12h_ampm.png
    reportes_bd/consumo_promedio_12h_ampm.csv
    reportes_bd/consumo_fecha_hora_12h_ampm.csv

El script solo ejecuta consultas SELECT. No modifica la base de datos.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from database.connection import get_connection


BASE_DIR = Path(__file__).resolve().parent
CARPETA_SALIDA = BASE_DIR / "reportes_bd"
CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)


def formato_12_horas(hora):
    """Convierte una hora de 0 a 23 al formato de 12 horas AM/PM."""
    if hora == 0:
        return "12 AM"
    if hora < 12:
        return f"{hora} AM"
    if hora == 12:
        return "12 PM"
    return f"{hora - 12} PM"


def cargar_consumo(connection):
    """Obtiene consumo agregado por fecha y hora desde PostgreSQL."""
    sql = """
        SELECT
            l.ts::date AS fecha,
            EXTRACT(HOUR FROM l.ts)::integer AS hora_24,
            COUNT(*)::bigint AS lecturas,
            ROUND(SUM(l.consumo_real_kwh)::numeric, 2)
                AS consumo_real_kwh,
            ROUND(SUM(COALESCE(l.consumo_kwh, 0))::numeric, 2)
                AS consumo_reportado_kwh
        FROM energia.lectura AS l
        GROUP BY
            l.ts::date,
            EXTRACT(HOUR FROM l.ts)
        ORDER BY
            fecha,
            hora_24;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        columnas = [columna.name for columna in cursor.description]
        filas = cursor.fetchall()

    df = pd.DataFrame(filas, columns=columnas)

    if df.empty:
        raise RuntimeError("energia.lectura no contiene registros.")

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["hora_24"] = pd.to_numeric(df["hora_24"]).astype(int)
    df["lecturas"] = pd.to_numeric(df["lecturas"]).astype(int)
    df["consumo_real_kwh"] = pd.to_numeric(df["consumo_real_kwh"])
    df["consumo_reportado_kwh"] = pd.to_numeric(
        df["consumo_reportado_kwh"]
    )
    df["hora_ampm"] = df["hora_24"].map(formato_12_horas)

    return df


def validar_cobertura(df):
    """Verifica que cada fecha tenga registros para las 24 horas."""
    horas_por_dia = df.groupby("fecha")["hora_24"].nunique()
    dias_incompletos = horas_por_dia[horas_por_dia != 24]

    print(f"[OK] Dias analizados: {df['fecha'].nunique():,}")
    print(f"[OK] Horas encontradas: {df['hora_24'].nunique():,} de 24")

    if dias_incompletos.empty:
        print("[OK] Todos los dias contienen las 24 horas.")
    else:
        print(
            f"[ADVERTENCIA] Hay {len(dias_incompletos):,} dias "
            "que no contienen las 24 horas."
        )


def crear_grafica(df):
    """Genera mapa de calor y curva promedio con etiquetas AM/PM."""
    matriz = (
        df.pivot(
            index="fecha",
            columns="hora_24",
            values="consumo_real_kwh",
        )
        .sort_index()
        .reindex(columns=range(24))
    )

    promedio = df.groupby("hora_24", as_index=False).agg(
        consumo_real_promedio=("consumo_real_kwh", "mean"),
        consumo_reportado_promedio=("consumo_reportado_kwh", "mean"),
        lecturas_promedio=("lecturas", "mean"),
    )
    promedio["hora_ampm"] = promedio["hora_24"].map(formato_12_horas)
    promedio["diferencia_kwh"] = (
        promedio["consumo_real_promedio"]
        - promedio["consumo_reportado_promedio"]
    )

    figura, (eje_mapa, eje_curva) = plt.subplots(
        2,
        1,
        figsize=(18, 12),
        gridspec_kw={"height_ratios": [2, 1]},
    )

    imagen = eje_mapa.imshow(
        matriz.to_numpy(),
        aspect="auto",
        interpolation="nearest",
        cmap="viridis",
    )
    eje_mapa.set_title(
        "Consumo real por fecha y hora, formato de 12 horas",
        fontsize=17,
        fontweight="bold",
    )
    eje_mapa.set_xlabel("Hora del dia")
    eje_mapa.set_ylabel("Fecha")
    eje_mapa.set_xticks(range(24))
    eje_mapa.set_xticklabels(
        [formato_12_horas(hora) for hora in range(24)],
        rotation=45,
        ha="right",
    )

    cantidad_dias = len(matriz.index)
    paso = max(1, cantidad_dias // 12)
    posiciones = list(range(0, cantidad_dias, paso))
    eje_mapa.set_yticks(posiciones)
    eje_mapa.set_yticklabels(
        [matriz.index[pos].strftime("%d %b %Y") for pos in posiciones]
    )

    barra_color = figura.colorbar(imagen, ax=eje_mapa, pad=0.02)
    barra_color.set_label("Consumo real total (kWh)")

    periodos = [
        (0, 5, "Madrugada", "#dbeafe"),
        (6, 11, "Manana", "#fef3c7"),
        (12, 17, "Tarde", "#dcfce7"),
        (18, 23, "Noche", "#ede9fe"),
    ]

    for inicio, fin, nombre, color in periodos:
        eje_curva.axvspan(
            inicio - 0.5,
            fin + 0.5,
            color=color,
            alpha=0.55,
            label=nombre,
        )

    eje_curva.plot(
        promedio["hora_24"],
        promedio["consumo_real_promedio"],
        marker="o",
        linewidth=2.6,
        label="Consumo real",
    )
    eje_curva.plot(
        promedio["hora_24"],
        promedio["consumo_reportado_promedio"],
        marker="o",
        linewidth=2.6,
        label="Consumo reportado",
    )

    fila_maxima = promedio.loc[
        promedio["consumo_real_promedio"].idxmax()
    ]
    fila_minima = promedio.loc[
        promedio["consumo_real_promedio"].idxmin()
    ]

    hora_maxima = int(fila_maxima["hora_24"])
    hora_minima = int(fila_minima["hora_24"])
    consumo_maximo = float(fila_maxima["consumo_real_promedio"])
    consumo_minimo = float(fila_minima["consumo_real_promedio"])

    texto_maximo = (
        "Pico: "
        + formato_12_horas(hora_maxima)
        + "\n"
        + f"{consumo_maximo:,.0f} kWh"
    )
    texto_minimo = (
        "Minimo: "
        + formato_12_horas(hora_minima)
        + "\n"
        + f"{consumo_minimo:,.0f} kWh"
    )

    eje_curva.annotate(
        texto_maximo,
        xy=(hora_maxima, consumo_maximo),
        xytext=(max(0, hora_maxima - 5), consumo_maximo * 1.025),
        arrowprops={"arrowstyle": "->"},
        fontweight="bold",
    )
    eje_curva.annotate(
        texto_minimo,
        xy=(hora_minima, consumo_minimo),
        xytext=(max(0, hora_minima - 5), consumo_minimo * 0.965),
        arrowprops={"arrowstyle": "->"},
        fontweight="bold",
    )

    eje_curva.set_title(
        "Perfil promedio de consumo en formato AM/PM",
        fontsize=17,
        fontweight="bold",
    )
    eje_curva.set_xlabel("Hora del dia")
    eje_curva.set_ylabel("Consumo total promedio (kWh)")
    eje_curva.set_xticks(range(24))
    eje_curva.set_xticklabels(
        [formato_12_horas(hora) for hora in range(24)],
        rotation=45,
        ha="right",
    )
    eje_curva.grid(True, axis="y", alpha=0.3)

    controles, etiquetas = eje_curva.get_legend_handles_labels()
    elementos_unicos = {}
    for control, etiqueta in zip(controles, etiquetas):
        elementos_unicos[etiqueta] = control

    eje_curva.legend(
        elementos_unicos.values(),
        elementos_unicos.keys(),
        ncol=3,
        loc="upper left",
        fontsize=9,
    )

    figura.suptitle(
        "Analisis del consumo electrico durante un dia completo",
        fontsize=20,
        fontweight="bold",
    )
    figura.tight_layout()

    ruta_grafica = CARPETA_SALIDA / "consumo_12h_ampm.png"
    figura.savefig(ruta_grafica, dpi=180, bbox_inches="tight")
    plt.close(figura)

    ruta_promedio = CARPETA_SALIDA / "consumo_promedio_12h_ampm.csv"
    promedio.to_csv(ruta_promedio, index=False, encoding="utf-8-sig")

    ruta_detalle = CARPETA_SALIDA / "consumo_fecha_hora_12h_ampm.csv"
    df.to_csv(ruta_detalle, index=False, encoding="utf-8-sig")

    print(f"[OK] Grafica: {ruta_grafica}")
    print(f"[OK] Promedio horario: {ruta_promedio}")
    print(f"[OK] Detalle fecha-hora: {ruta_detalle}")
    print(
        f"[RESUMEN] Pico: {formato_12_horas(hora_maxima)} "
        f"con {consumo_maximo:,.2f} kWh."
    )
    print(
        f"[RESUMEN] Minimo: {formato_12_horas(hora_minima)} "
        f"con {consumo_minimo:,.2f} kWh."
    )


def main():
    print("=" * 68)
    print("CONSUMO POR HORA EN FORMATO DE 12 HORAS AM/PM")
    print("=" * 68)

    connection = get_connection()

    try:
        print("Consultando PostgreSQL...")
        datos = cargar_consumo(connection)
        validar_cobertura(datos)
        crear_grafica(datos)
        print("[OK] Analisis finalizado correctamente.")
    finally:
        connection.close()
        print("[OK] Conexion PostgreSQL cerrada.")


if __name__ == "__main__":
    main()
