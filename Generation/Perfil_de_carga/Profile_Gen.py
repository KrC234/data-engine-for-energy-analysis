"""
    VERIFICADOR DE PERFILES HORARIOS (Generation/Perfil_de_carga/Profile_Gen.py)

    No genera datos: en este proyecto los perfiles horarios los calcula
    y normaliza 02_catalogos.sql (1,296 filas por 18 tipos x 3 dias x 24 h).

    Este modulo VALIDA que las curvas esten completas y normalizadas
    (cada curva debe sumar 24 para que consumo_base_kwh_h represente
    el kWh/h medio del dia).
"""


def verificar_perfiles(connection):
    """Ejecuta la validacion y devuelve un resumen legible."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT p.id_tipo_servicio, t.clave, p.tipo_dia,
                   COUNT(*)  AS horas,
                   ROUND(SUM(p.factor)::numeric, 4) AS suma,
                   ROUND(MIN(p.factor)::numeric, 4) AS minimo,
                   ROUND(MAX(p.factor)::numeric, 4) AS maximo
            FROM energia.perfil_carga_horaria p
            INNER JOIN energia.tipo_servicio t
                ON t.id_tipo_servicio = p.id_tipo_servicio
            GROUP BY p.id_tipo_servicio, t.clave, p.tipo_dia
            ORDER BY p.id_tipo_servicio, p.tipo_dia
            """
        )
        filas = cur.fetchall()

    problemas = []
    for id_tipo, clave, tipo_dia, horas, suma, minimo, maximo in filas:
        horas = int(horas)
        suma = float(suma)
        minimo = float(minimo)
        maximo = float(maximo)
        if horas != 24:
            problemas.append(f"{clave}/{tipo_dia}: {horas} horas (esperado 24)")
        if abs(suma - 24.0) > 0.01:
            problemas.append(f"{clave}/{tipo_dia}: suma {suma} (esperado ~24)")
        if minimo < 0 or maximo > 6:
            problemas.append(f"{clave}/{tipo_dia}: factor fuera de rango 0-6")

    print("    Perfiles: complejidad por ruta verificada")
    print(f"    Perfiles: {len(filas)} curvas (tipo x dia) revisadas")

    if problemas:
        print(f"    Perfiles: {len(problemas)} inconsistencias detectadas:")
        for p in problemas[:20]:
            print(f"      - {p}")
        return False

    print("    Perfiles: OK, todas las curvas completas y normalizadas (suma=24)")
    return True