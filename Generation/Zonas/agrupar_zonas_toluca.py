from pathlib import Path

import pandas as pd


"""
AGRUPACION DE LOCALIDADES REALES DE TOLUCA

Este script toma el archivo GRS_AGEB_Toluca_calibrado.csv,
que contiene una fila por cada AGEB urbana de Toluca, y agrupa
las filas que pertenecen a una misma localidad.

Por ejemplo, Sauces aparece en varias filas porque contiene
varias AGEB. El script junta todas esas filas y genera un solo
registro para la localidad Sauces.

Para cada localidad se calculan:

- Poblacion total.
- Viviendas habitadas totales.
- Grado de rezago social representativo.
- Factor socioeconomico ponderado por viviendas.

El script no calcula servicios electricos, porque la base
de CONEVAL no contiene contratos, medidores ni puntos de
consumo electrico.

El campo n_servicios_previstos se definira posteriormente
durante la corrida maestra del proyecto.

El archivo original no se modifica.

Archivo de entrada:
Test/Testing_data/GRS_AGEB_Toluca_calibrado.csv

Archivo generado:
Test/Testing_data/Zonas_Toluca_agrupadas.csv
"""


# ==========================================================
# RUTAS RELATIVAS AL PROYECTO
# ==========================================================

# Este script se encuentra en:
# Generation/Zonas/agrupar_zonas_toluca.py
#
# parents[2] permite llegar a la raiz del proyecto:
# data-engine-for-energy-analysis/

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]

ARCHIVO_ENTRADA = (
    RAIZ_PROYECTO
    / "Test"
    / "Testing_data"
    / "GRS_AGEB_Toluca_calibrado.csv"
)

ARCHIVO_SALIDA = (
    RAIZ_PROYECTO
    / "Test"
    / "Testing_data"
    / "Zonas_Toluca_agrupadas.csv"
)


# ==========================================================
# CARGA DE DATOS
# ==========================================================

def cargar_datos():
    """
    Abre el CSV generado por calcular_factores_toluca.py.
    """

    print("=" * 70)
    print("AGRUPACION DE LOCALIDADES DE TOLUCA")
    print("=" * 70)

    print(f"\nArchivo de entrada:\n{ARCHIVO_ENTRADA}")

    if not ARCHIVO_ENTRADA.exists():
        raise FileNotFoundError(
            "\nNo se encontro el archivo de entrada.\n\n"
            f"Ruta esperada:\n{ARCHIVO_ENTRADA}\n\n"
            "Primero ejecuta calcular_factores_toluca.py."
        )

    datos = pd.read_csv(
        ARCHIVO_ENTRADA,
        encoding="utf-8-sig",
        low_memory=False
    )

    if datos.empty:
        raise ValueError(
            "El archivo de entrada existe, pero esta vacio."
        )

    print(f"\nRegistros cargados: {len(datos):,}")

    return datos


# ==========================================================
# VALIDACION DE COLUMNAS
# ==========================================================

def validar_columnas(datos):
    """
    Comprueba que el archivo tenga las columnas necesarias
    para realizar la agrupacion.
    """

    columnas_requeridas = {
        "nombre_localidad",
        "poblacion_total",
        "viviendas_habitadas",
        "grado_rezago_social",
        "factor_socioeconomico"
    }

    columnas_faltantes = (
        columnas_requeridas - set(datos.columns)
    )

    if columnas_faltantes:
        lista_faltantes = "\n".join(
            f"- {columna}"
            for columna in sorted(columnas_faltantes)
        )

        raise ValueError(
            "\nEl archivo no contiene todas las columnas "
            "necesarias.\n\n"
            f"Columnas faltantes:\n{lista_faltantes}"
        )

    print("Columnas requeridas: OK")


# ==========================================================
# LIMPIEZA DE DATOS
# ==========================================================

def limpiar_datos(datos):
    """
    Limpia las columnas necesarias antes de agrupar.
    """

    datos = datos.copy()

    # Limpiar columnas de texto.
    columnas_texto = [
        "nombre_localidad",
        "grado_rezago_social"
    ]

    for columna in columnas_texto:
        datos[columna] = (
            datos[columna]
            .astype(str)
            .str.strip()
        )

    # Convertir columnas cuantitativas a valores numericos.
    columnas_numericas = [
        "poblacion_total",
        "viviendas_habitadas",
        "factor_socioeconomico"
    ]

    for columna in columnas_numericas:
        datos[columna] = pd.to_numeric(
            datos[columna],
            errors="coerce"
        )

    # Eliminar registros sin valores indispensables.
    datos = datos.dropna(
        subset=[
            "poblacion_total",
            "viviendas_habitadas",
            "factor_socioeconomico"
        ]
    ).copy()

    # Eliminar localidades sin nombre.
    datos = datos[
        (datos["nombre_localidad"] != "")
        & (datos["nombre_localidad"].str.lower() != "nan")
    ].copy()

    # Eliminar registros con cantidades negativas.
    datos = datos[
        (datos["poblacion_total"] >= 0)
        & (datos["viviendas_habitadas"] >= 0)
    ].copy()

    if datos.empty:
        raise ValueError(
            "No quedaron registros validos despues de limpiar."
        )

    print(
        f"Registros validos despues de limpiar: "
        f"{len(datos):,}"
    )

    return datos


# ==========================================================
# FACTOR SOCIOECONOMICO PONDERADO
# ==========================================================

def calcular_factor_ponderado(grupo):
    """
    Calcula el factor socioeconomico de una localidad.

    Formula:

        suma(factor de cada fila * viviendas de cada fila)
        ---------------------------------------------------
                  viviendas totales de la localidad

    Las filas con mas viviendas tienen mayor peso en el
    resultado que las filas con pocas viviendas.
    """

    total_viviendas = (
        grupo["viviendas_habitadas"].sum()
    )

    # Si no hay viviendas, se utiliza el promedio simple.
    if total_viviendas <= 0:
        return grupo["factor_socioeconomico"].mean()

    suma_ponderada = (
        grupo["factor_socioeconomico"]
        * grupo["viviendas_habitadas"]
    ).sum()

    return suma_ponderada / total_viviendas


# ==========================================================
# REZAGO REPRESENTATIVO
# ==========================================================

def obtener_rezago_representativo(grupo):
    """
    Selecciona el grado de rezago que representa la mayor
    cantidad de viviendas dentro de la localidad.

    Ejemplo:

    Si la mayor cantidad de viviendas esta en registros con
    rezago Bajo, el grado representativo de la localidad
    sera Bajo.
    """

    viviendas_por_rezago = (
        grupo.groupby("grado_rezago_social")[
            "viviendas_habitadas"
        ]
        .sum()
        .sort_values(ascending=False)
    )

    if viviendas_por_rezago.empty:
        return "Sin clasificacion"

    return viviendas_por_rezago.index[0]


# ==========================================================
# AGRUPACION POR LOCALIDAD
# ==========================================================

def agrupar_localidades(datos):
    """
    Agrupa todas las filas que tienen el mismo nombre de
    localidad.

    El resultado contiene una sola fila por cada localidad.
    """

    registros_agrupados = []

    grupos = datos.groupby(
        "nombre_localidad",
        sort=True
    )

    for nombre_localidad, grupo in grupos:

        # Sumar la poblacion de todos los registros
        # correspondientes a la localidad.
        poblacion_total = (
            grupo["poblacion_total"].sum()
        )

        # Sumar las viviendas de todos los registros
        # correspondientes a la localidad.
        viviendas_totales = (
            grupo["viviendas_habitadas"].sum()
        )

        # Calcular el factor ponderado por viviendas.
        factor_ponderado = (
            calcular_factor_ponderado(grupo)
        )

        # Obtener el grado de rezago representativo.
        rezago_representativo = (
            obtener_rezago_representativo(grupo)
        )

        registros_agrupados.append(
            {
                "nombre_localidad": nombre_localidad,
                "poblacion_total": int(
                    round(poblacion_total)
                ),
                "viviendas_habitadas": int(
                    round(viviendas_totales)
                ),
                "grado_rezago_representativo":
                    rezago_representativo,
                "factor_socioeconomico": round(
                    float(factor_ponderado),
                    3
                )
            }
        )

    resultado = pd.DataFrame(
        registros_agrupados
    )

    if resultado.empty:
        raise ValueError(
            "No fue posible generar localidades agrupadas."
        )

    # Ordenar las localidades de mayor a menor poblacion.
    resultado = resultado.sort_values(
        by=[
            "poblacion_total",
            "nombre_localidad"
        ],
        ascending=[
            False,
            True
        ]
    ).reset_index(drop=True)

    # Agregar un identificador consecutivo.
    resultado.insert(
        0,
        "id_referencia",
        range(1, len(resultado) + 1)
    )

    print(
        f"Localidades agrupadas: {len(resultado):,}"
    )

    return resultado


# ==========================================================
# MOSTRAR RESULTADOS
# ==========================================================

def mostrar_resultados(resultado):
    """
    Muestra un resumen de las localidades agrupadas.
    """

    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)

    print(
        f"\nLocalidades reales encontradas: "
        f"{len(resultado):,}"
    )

    print(
        f"Poblacion total agrupada: "
        f"{resultado['poblacion_total'].sum():,.0f}"
    )

    print(
        f"Viviendas agrupadas: "
        f"{resultado['viviendas_habitadas'].sum():,.0f}"
    )

    print("\nLocalidades por grado de rezago:")
    print("-" * 70)

    print(
        resultado[
            "grado_rezago_representativo"
        ]
        .value_counts()
        .to_string()
    )

    columnas_muestra = [
        "id_referencia",
        "nombre_localidad",
        "poblacion_total",
        "viviendas_habitadas",
        "grado_rezago_representativo",
        "factor_socioeconomico"
    ]

    print("\nPrimeras 20 localidades:")
    print("-" * 70)

    print(
        resultado[columnas_muestra]
        .head(20)
        .to_string(index=False)
    )


# ==========================================================
# GUARDAR RESULTADOS
# ==========================================================

def guardar_resultados(resultado):
    """
    Guarda una fila por cada localidad.

    El archivo generado no contiene:

    - Clave de localidad.
    - Claves de AGEB.
    - Cantidad de AGEB.
    - Servicios propuestos.
    """

    ARCHIVO_SALIDA.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    resultado.to_csv(
        ARCHIVO_SALIDA,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n" + "=" * 70)
    print("ARCHIVO GENERADO")
    print("=" * 70)

    print(f"\n{ARCHIVO_SALIDA}")
    print("\nProceso terminado correctamente.")


# ==========================================================
# PROGRAMA PRINCIPAL
# ==========================================================

def main():
    """
    Ejecuta el proceso completo de agrupacion.
    """

    # 1. Cargar el CSV de Toluca.
    datos = cargar_datos()

    # 2. Validar las columnas necesarias.
    validar_columnas(datos)

    # 3. Limpiar los registros.
    datos = limpiar_datos(datos)

    # 4. Agrupar por nombre de localidad.
    resultado = agrupar_localidades(datos)

    # 5. Mostrar el resumen.
    mostrar_resultados(resultado)

    # 6. Guardar el nuevo CSV.
    guardar_resultados(resultado)


if __name__ == "__main__":
    main()