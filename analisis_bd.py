"""Genera graficas y validaciones de HyperDataSynthetic."""

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
from database.connection import get_connection

BASE_DIR = Path(__file__).resolve().parent
SALIDA = BASE_DIR / "reportes_bd"
SALIDA.mkdir(parents=True, exist_ok=True)


def consultar(connection, sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)
        columnas = [col.name for col in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=columnas)


def exportar(df, nombre):
    ruta = SALIDA / f"{nombre}.csv"
    df.to_csv(ruta, index=False, encoding="utf-8-sig")
    print(f"[OK] CSV: {ruta}")


def guardar(nombre):
    ruta = SALIDA / f"{nombre}.png"
    plt.tight_layout()
    plt.savefig(ruta, dpi=160, bbox_inches="tight")
    plt.close()
    print(f"[OK] Grafica: {ruta}")


def conteos(connection):
    df = consultar(connection, """
        SELECT 'Calendario' tabla, COUNT(*)::bigint registros FROM energia.calendario
        UNION ALL SELECT 'Perfiles', COUNT(*) FROM energia.perfil_carga_horaria
        UNION ALL SELECT 'Servicios', COUNT(*) FROM energia.servicio
        UNION ALL SELECT 'Medidores', COUNT(*) FROM energia.medidor
        UNION ALL SELECT 'Eventos', COUNT(*) FROM energia.evento
        UNION ALL SELECT 'Lecturas', COUNT(*) FROM energia.lectura
        UNION ALL SELECT 'Alertas', COUNT(*) FROM energia.alerta
        UNION ALL SELECT 'Facturacion', COUNT(*) FROM energia.periodo_facturacion
        ORDER BY registros DESC
    """)
    exportar(df, "01_conteos")
    plt.figure(figsize=(11, 6))
    barras = plt.bar(df["tabla"], df["registros"])
    plt.title("Registros por tabla")
    plt.xlabel("Tabla")
    plt.ylabel("Registros")
    plt.xticks(rotation=35, ha="right")
    plt.ticklabel_format(style="plain", axis="y")
    for b, v in zip(barras, df["registros"]):
        plt.text(b.get_x() + b.get_width()/2, b.get_height(), f"{int(v):,}",
                 ha="center", va="bottom", fontsize=8)
    guardar("01_conteos")


def servicios_categoria(connection):
    df = consultar(connection, """
        SELECT ts.categoria, COUNT(*)::bigint servicios
        FROM energia.servicio s
        JOIN energia.tipo_servicio ts USING (id_tipo_servicio)
        GROUP BY ts.categoria ORDER BY servicios DESC
    """)
    exportar(df, "02_servicios_categoria")
    plt.figure(figsize=(10, 6))
    plt.bar(df["categoria"], df["servicios"])
    plt.title("Servicios por categoria")
    plt.xlabel("Categoria")
    plt.ylabel("Servicios")
    plt.xticks(rotation=35, ha="right")
    guardar("02_servicios_categoria")


def top_zonas(connection):
    df = consultar(connection, """
        SELECT z.nombre zona, COUNT(s.id_servicio)::bigint servicios
        FROM energia.zona z
        LEFT JOIN energia.servicio s USING (id_zona)
        GROUP BY z.id_zona, z.nombre
        ORDER BY servicios DESC LIMIT 15
    """)
    exportar(df, "03_top_zonas")
    df = df.sort_values("servicios")
    plt.figure(figsize=(11, 7))
    plt.barh(df["zona"], df["servicios"])
    plt.title("Top 15 zonas por servicios")
    plt.xlabel("Servicios")
    guardar("03_top_zonas")


def eventos_tipo(connection):
    df = consultar(connection, """
        SELECT te.nombre tipo_evento, COUNT(*)::bigint eventos
        FROM energia.evento e
        JOIN energia.tipo_evento te USING (id_tipo_evento)
        GROUP BY te.id_tipo_evento, te.nombre
        ORDER BY eventos DESC
    """)
    exportar(df, "04_eventos_tipo")
    df = df.sort_values("eventos")
    plt.figure(figsize=(11, 6))
    plt.barh(df["tipo_evento"], df["eventos"])
    plt.title("Eventos por tipo")
    plt.xlabel("Eventos")
    guardar("04_eventos_tipo")


def consumo_diario(connection):
    df = consultar(connection, """
        SELECT ts::date fecha,
               COUNT(*)::bigint lecturas,
               ROUND(SUM(consumo_real_kwh)::numeric, 2) consumo_real_kwh,
               ROUND(SUM(COALESCE(consumo_kwh, 0))::numeric, 2) consumo_reportado_kwh
        FROM energia.lectura
        GROUP BY ts::date ORDER BY fecha
    """)
    df["fecha"] = pd.to_datetime(df["fecha"])
    for c in ["consumo_real_kwh", "consumo_reportado_kwh"]:
        df[c] = pd.to_numeric(df[c])
    exportar(df, "05_consumo_diario")

    plt.figure(figsize=(13, 6))
    plt.plot(df["fecha"], df["lecturas"])
    plt.title("Lecturas por dia")
    plt.xlabel("Fecha")
    plt.ylabel("Lecturas")
    plt.ticklabel_format(style="plain", axis="y")
    guardar("05_lecturas_dia")

    plt.figure(figsize=(13, 6))
    plt.plot(df["fecha"], df["consumo_real_kwh"], label="Real")
    plt.plot(df["fecha"], df["consumo_reportado_kwh"], label="Reportado")
    plt.title("Consumo real y reportado por dia")
    plt.xlabel("Fecha")
    plt.ylabel("kWh")
    plt.legend()
    guardar("06_consumo_diario")


def curva_horaria(connection):
    df = consultar(connection, """
        SELECT EXTRACT(HOUR FROM ts)::integer hora,
               ROUND(AVG(consumo_real_kwh)::numeric, 4) promedio_real_kwh,
               ROUND(AVG(consumo_kwh)::numeric, 4) promedio_reportado_kwh
        FROM energia.lectura
        GROUP BY EXTRACT(HOUR FROM ts) ORDER BY hora
    """)
    for c in ["promedio_real_kwh", "promedio_reportado_kwh"]:
        df[c] = pd.to_numeric(df[c])
    exportar(df, "07_curva_horaria")
    plt.figure(figsize=(11, 6))
    plt.plot(df["hora"], df["promedio_real_kwh"], marker="o", label="Real")
    plt.plot(df["hora"], df["promedio_reportado_kwh"], marker="o", label="Reportado")
    plt.title("Curva horaria promedio")
    plt.xlabel("Hora")
    plt.ylabel("Consumo promedio (kWh)")
    plt.xticks(range(24))
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar("07_curva_horaria")


def curva_categoria(connection):
    df = consultar(connection, """
        SELECT tsrv.categoria,
               EXTRACT(HOUR FROM l.ts)::integer hora,
               ROUND(AVG(l.consumo_real_kwh)::numeric, 4) consumo_promedio_kwh
        FROM energia.lectura l
        JOIN energia.medidor m USING (id_medidor)
        JOIN energia.servicio s USING (id_servicio)
        JOIN energia.tipo_servicio tsrv USING (id_tipo_servicio)
        GROUP BY tsrv.categoria, EXTRACT(HOUR FROM l.ts)
        ORDER BY tsrv.categoria, hora
    """)
    df["consumo_promedio_kwh"] = pd.to_numeric(df["consumo_promedio_kwh"])
    exportar(df, "08_curva_categoria")
    plt.figure(figsize=(13, 7))
    for categoria, grupo in df.groupby("categoria"):
        plt.plot(grupo["hora"], grupo["consumo_promedio_kwh"], marker="o", label=categoria)
    plt.title("Curva horaria por categoria")
    plt.xlabel("Hora")
    plt.ylabel("Consumo promedio (kWh)")
    plt.xticks(range(24))
    plt.grid(True, alpha=0.3)
    plt.legend()
    guardar("08_curva_categoria")


def validaciones(connection):
    df = consultar(connection, """
        SELECT 'medidores_sin_servicio' validacion, COUNT(*)::bigint inconsistencias
        FROM energia.medidor m LEFT JOIN energia.servicio s USING (id_servicio)
        WHERE s.id_servicio IS NULL
        UNION ALL
        SELECT 'eventos_sin_medidor', COUNT(*)
        FROM energia.evento e LEFT JOIN energia.medidor m USING (id_medidor)
        WHERE m.id_medidor IS NULL
        UNION ALL
        SELECT 'lecturas_sin_medidor', COUNT(*)
        FROM energia.lectura l LEFT JOIN energia.medidor m USING (id_medidor)
        WHERE m.id_medidor IS NULL
        UNION ALL
        SELECT 'eventos_fechas_invalidas', COUNT(*) FROM energia.evento WHERE ts_fin <= ts_inicio
        UNION ALL
        SELECT 'lecturas_reales_negativas', COUNT(*) FROM energia.lectura WHERE consumo_real_kwh < 0
        UNION ALL
        SELECT 'lecturas_reales_nulas', COUNT(*) FROM energia.lectura WHERE consumo_real_kwh IS NULL
        UNION ALL
        SELECT 'calidad_enlace_invalida', COUNT(*) FROM energia.medidor
        WHERE calidad_enlace IS NULL OR calidad_enlace < 0 OR calidad_enlace > 1
        ORDER BY validacion
    """)
    exportar(df, "09_validaciones")
    print("\nVALIDACIONES")
    print(df.to_string(index=False))
    total = int(df["inconsistencias"].sum())
    print("[OK] Sin inconsistencias." if total == 0 else f"[ADVERTENCIA] {total:,} inconsistencias.")


def main():
    print("=" * 65)
    print("ANALISIS VISUAL DE HYPERDATASYNTHETIC")
    print("=" * 65)
    print(f"Carpeta de salida: {SALIDA}")
    connection = get_connection()
    try:
        conteos(connection)
        servicios_categoria(connection)
        top_zonas(connection)
        eventos_tipo(connection)
        consumo_diario(connection)
        curva_horaria(connection)
        curva_categoria(connection)
        validaciones(connection)
        print("\n[OK] Analisis terminado.")
    finally:
        connection.close()
        print("[OK] Conexion cerrada.")


if __name__ == "__main__":
    main()
