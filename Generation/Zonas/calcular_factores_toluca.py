from pathlib import Path

import pandas as pd


"""
CALIBRACION DEL FACTOR SOCIOECONOMICO

Este script carga la base oficial de Grado de Rezago Social
por AGEB urbana 2020 de CONEVAL, selecciona solamente los
registros del municipio de Toluca y convierte el grado de
rezago social en un factor socioeconomico compatible con
HyperDataSynthetic.

La relacion utilizada es inversa:

- Muy bajo rezago -> factor 2.000
- Bajo rezago     -> factor 1.625
- Medio rezago    -> factor 1.250
- Alto rezago     -> factor 0.875
- Muy alto rezago -> factor 0.500

El Grado de Rezago Social es un indicador oficial de CONEVAL.
La conversion al factor socioeconomico es una regla interna
del proyecto HyperDataSynthetic.

Fuente:
https://www.coneval.org.mx/Medicion/IRS/Paginas/Rezago_social_AGEB_2020.aspx

Descarga:
https://www.coneval.org.mx/Medicion/Documents/GRS_AGEB_2020/GRS_AGEB_urbana_2020.zip

Referencia geografica de Toluca:
https://gaia.inegi.org.mx/wscatgeo/v2/mgem/15/106
"""


# ==========================================================
# RUTAS RELATIVAS AL PROYECTO
# ==========================================================

# El script est├í en:
# Generation/Zonas/calcular_factores_toluca.py
#
# parents[2] apunta a la ra├¡z del repositorio.

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]

ARCHIVO_ENTRADA = (
    RAIZ_PROYECTO
    / "Test"
    / "Testing_data"
    / "GRS_AGEB_urbana_2020.xlsx"
)

ARCHIVO_SALIDA = (
    RAIZ_PROYECTO
    / "Test"
    / "Testing_data"
    / "GRS_AGEB_Toluca_calibrado.csv"
)


# ==========================================================
# CLAVES GEOGRAFICAS
# ==========================================================

CLAVE_ENTIDAD = "15"
CLAVE_MUNICIPIO = "15106"


# ==========================================================
# NOMBRES DE LAS 28 COLUMNAS DEL EXCEL
# ==========================================================

COLUMNAS = [
    "clave_entidad",
    "entidad_federativa",
    "clave_municipio",
    "nombre_municipio",
    "clave_localidad",
    "nombre_localidad",
    "folio_ageb",
    "clave_ageb",
    "poblacion_total",
    "viviendas_habitadas",
    "i_analfabetismo",
    "i_inasistencia_6_14",
    "i_inasistencia_15_24",
    "i_educacion_basica_incompleta",
    "i_sin_servicios_salud",
    "i_hacinamiento",
    "i_sin_agua",
    "i_sin_sanitario",
    "i_sin_drenaje",
    "i_sin_electricidad",
    "i_piso_tierra",
    "i_sin_lavadora",
    "i_sin_refrigerador",
    "i_sin_telefono_fijo",
    "i_sin_celular",
    "i_sin_computadora",
    "i_sin_internet",
    "grado_rezago_social",
]


# ==========================================================
# CONVERSION DEL REZAGO AL FACTOR HSD
# ==========================================================

FACTORES_POR_REZAGO = {
    "Muy bajo": 2.000,
    "Bajo": 1.625,
    "Medio": 1.250,
    "Alto": 0.875,
    "Muy alto": 0.500,
}


def cargar_datos():
    """
    Carga el Excel de CONEVAL.

    El archivo tiene:
    - T├¡tulo en la fila 2.
    - Encabezados en las filas 4 y 5.
    - Datos a partir de la fila 7.

    Por esa raz├│n se omiten las primeras seis filas y se
    asignan manualmente los nombres de las 28 columnas.
    """

    if not ARCHIVO_ENTRADA.exists():
        raise FileNotFoundError(
            "\nNo se encontr├│ el archivo de entrada.\n\n"
            f"Ruta esperada:\n{ARCHIVO_ENTRADA}"
        )

    print("=" * 65)
    print("CALIBRACION SOCIOECONOMICA DE TOLUCA")
    print("=" * 65)

    print(f"\nArchivo de entrada:\n{ARCHIVO_ENTRADA}")

    datos = pd.read_excel(
        ARCHIVO_ENTRADA,
        sheet_name="GRS 2020",
        header=None,
        skiprows=6,
        names=COLUMNAS,
        engine="openpyxl",
        dtype={
            "clave_entidad": str,
            "clave_municipio": str,
            "clave_localidad": str,
            "folio_ageb": str,
            "clave_ageb": str,
        },
    )

    # Elimina filas completamente vac├¡as.
    datos = datos.dropna(how="all").copy()

    # Limpia espacios en las claves.
    datos["clave_entidad"] = (
        datos["clave_entidad"]
        .astype(str)
        .str.strip()
        .str.zfill(2)
    )

    datos["clave_municipio"] = (
        datos["clave_municipio"]
        .astype(str)
        .str.strip()
        .str.zfill(5)
    )

    print(f"\nRegistros cargados: {len(datos):,}")

    return datos


def obtener_toluca(datos):
    """
    Filtra las AGEB del municipio de Toluca.

    Estado de M├®xico:
        clave_entidad = 15

    Toluca:
        clave_municipio = 15106
    """

    toluca = datos[
        (datos["clave_entidad"] == CLAVE_ENTIDAD)
        & (datos["clave_municipio"] == CLAVE_MUNICIPIO)
    ].copy()

    if toluca.empty:
        raise ValueError(
            "\nNo se encontraron AGEB de Toluca.\n\n"
            "Filtro utilizado:\n"
            "clave_entidad = 15\n"
            "clave_municipio = 15106"
        )

    print(f"AGEB encontradas para Toluca: {len(toluca):,}")

    return toluca


def calcular_factor_socioeconomico(toluca):
    """
    Convierte el Grado de Rezago Social al factor interno
    utilizado por HyperDataSynthetic.
    """

    resultado = toluca.copy()

    resultado["grado_rezago_social"] = (
        resultado["grado_rezago_social"]
        .astype(str)
        .str.strip()
    )

    resultado["factor_socioeconomico"] = (
        resultado["grado_rezago_social"]
        .map(FACTORES_POR_REZAGO)
    )

    # Registros cuyo grado no pudo convertirse.
    no_convertidos = resultado[
        resultado["factor_socioeconomico"].isna()
    ]

    if not no_convertidos.empty:
        print(
            "\nAdvertencia: se eliminar├ín "
            f"{len(no_convertidos):,} registros sin grado v├ílido."
        )

    resultado = resultado.dropna(
        subset=["factor_socioeconomico"]
    ).copy()

    if resultado.empty:
        raise ValueError(
            "No existen AGEB de Toluca con un grado de "
            "rezago social v├ílido."
        )

    resultado["factor_socioeconomico"] = (
        resultado["factor_socioeconomico"]
        .astype(float)
        .round(3)
    )

    return resultado


def mostrar_resultados(resultado):
    """
    Muestra un resumen de los resultados calculados.
    """

    print("\n" + "=" * 65)
    print("RESULTADOS")
    print("=" * 65)

    print(f"\nAGEB procesadas: {len(resultado):,}")

    print("\nDistribuci├│n por grado de rezago:")
    print("-" * 65)

    distribucion = (
        resultado["grado_rezago_social"]
        .value_counts()
        .reindex(
            [
                "Muy bajo",
                "Bajo",
                "Medio",
                "Alto",
                "Muy alto",
            ],
            fill_value=0,
        )
    )

    print(distribucion.to_string())

    print("\nFactores asignados:")
    print("-" * 65)

    resumen = (
        resultado[
            [
                "grado_rezago_social",
                "factor_socioeconomico",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            "factor_socioeconomico",
            ascending=False,
        )
    )

    print(resumen.to_string(index=False))

    print("\nPrimeras 20 AGEB de Toluca:")
    print("-" * 65)

    columnas_muestra = [
        "clave_ageb",
        "nombre_localidad",
        "poblacion_total",
        "viviendas_habitadas",
        "grado_rezago_social",
        "factor_socioeconomico",
    ]

    print(
        resultado[columnas_muestra]
        .head(20)
        .to_string(index=False)
    )


def guardar_resultados(resultado):
    """
    Guarda los resultados de Toluca en formato CSV.
    """

    resultado.to_csv(
        ARCHIVO_SALIDA,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 65)
    print("ARCHIVO GENERADO")
    print("=" * 65)

    print(f"\n{ARCHIVO_SALIDA}")
    print("\nProceso terminado correctamente.")


def main():
    """
    Ejecuta todo el proceso.
    """

    datos = cargar_datos()

    toluca = obtener_toluca(datos)

    resultado = calcular_factor_socioeconomico(toluca)

    mostrar_resultados(resultado)

    guardar_resultados(resultado)


if __name__ == "__main__":
    main()
