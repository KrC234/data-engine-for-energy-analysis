from pathlib import Path

import pandas as pd


"""
AGRUPACION DE ZONAS REALES DE TOLUCA

Este script toma el archivo GRS_AGEB_Toluca_calibrado.csv,
que contiene una fila por cada AGEB urbana de Toluca, y agrupa
las AGEB que pertenecen a la misma localidad.

Por ejemplo, Sauces aparece en varias filas porque contiene
varias AGEB. El script junta todas esas filas y genera un solo
registro para la localidad Sauces.

Para cada localidad se calculan:

- Cantidad de AGEB.
- Poblacion total.
- Viviendas habitadas totales.
- Grado de rezago social representativo.
- Factor socioeconomico ponderado por viviendas.
- Lista de las AGEB utilizadas.
- Servicios propuestos de forma proporcional.

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
# CONFIGURACION
# ==========================================================

# Cuota aproximada asignada al bloque de Ramiro.
#
# El script distribuye estos 833 servicios entre todas
# las localidades, usando las viviendas como referencia.
#
# Si no quieres distribuir servicios, cambia 833 por None.

TOTAL_SERVICIOS_RAMIRO = 833


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

    print(f"\nRegistros AGEB cargados: {len(datos):,}")

    return datos


# ==========================================================
# VALIDACION DE COLUMNAS
# ==========================================================

def validar_columnas(datos):
    """
    Comprueba que el archivo tenga las columnas necesarias.
    """

    columnas_requeridas = {
        "clave_localidad",
        "nombre_localidad",
        "clave_ageb",
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

    Las claves se conservan como texto para no perder ceros
    o letras presentes en algunas claves de AGEB.
    """

    datos = datos.copy()

    columnas_texto = [
        "clave_localidad",
        "nombre_localidad",
        "clave_ageb",
        "grado_rezago_social"
    ]

    for columna in columnas_texto:
        datos[columna] = (
            datos[columna]
            .astype(str)
            .str.strip()
        )

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

    # Elimina filas que no contienen datos indispensables.
    datos = datos.dropna(
        subset=[
            "poblacion_total",
            "viviendas_habitadas",
            "factor_socioeconomico"
        ]
    ).copy()

    # Elimina nombres vacios o convertidos desde valores nulos.
    datos = datos[
        (datos["nombre_localidad"] != "")
        & (datos["nombre_localidad"].str.lower() != "nan")
    ].copy()

    # Solo se aceptan valores no negativos.
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
    Calcula el factor de toda una localidad.

    Formula:

        suma(factor de AGEB * viviendas de AGEB)
        -----------------------------------------
              viviendas totales de localidad

    De esta manera, una AGEB con muchas viviendas tiene mayor
    peso que una AGEB con pocas viviendas.
    """

    total_viviendas = (
        grupo["viviendas_habitadas"].sum()
    )

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
# LISTA DE AGEB
# ==========================================================

def obtener_lista_ageb(grupo):
    """
    Reune las claves de AGEB de cada localidad en un texto.
    """

    claves = sorted(
        grupo["clave_ageb"]
        .dropna()
        .astype(str)
        .unique()
    )

    return ", ".join(claves)


# ==========================================================
# AGRUPACION POR LOCALIDAD
# ==========================================================

def agrupar_localidades(datos):
    """
    Agrupa las AGEB que tienen la misma clave de localidad.

    El resultado contiene una fila por cada localidad real.
    """

    registros_agrupados = []

    grupos = datos.groupby(
        [
            "clave_localidad",
            "nombre_localidad"
        ],
        sort=True
    )

    for (
        clave_localidad,
        nombre_localidad
    ), grupo in grupos:

        poblacion_total = (
            grupo["poblacion_total"].sum()
        )

        viviendas_totales = (
            grupo["viviendas_habitadas"].sum()
        )

        cantidad_ageb = (
            grupo["clave_ageb"].nunique()
        )

        factor_ponderado = (
            calcular_factor_ponderado(grupo)
        )

        rezago_representativo = (
            obtener_rezago_representativo(grupo)
        )

        claves_ageb = obtener_lista_ageb(grupo)

        registros_agrupados.append(
            {
                "clave_localidad": clave_localidad,
                "nombre_localidad": nombre_localidad,
                "cantidad_ageb": int(cantidad_ageb),
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
                ),
                "claves_ageb": claves_ageb
            }
        )

    resultado = pd.DataFrame(
        registros_agrupados
    )

    if resultado.empty:
        raise ValueError(
            "No fue posible generar localidades agrupadas."
        )

    # Ordenar de mayor a menor poblacion.
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
# DISTRIBUCION PROPORCIONAL DE SERVICIOS
# ==========================================================

def asignar_servicios_proporcionales(
    resultado,
    total_servicios
):
    """
    Reparte los servicios entre las localidades según su
    cantidad de viviendas.

    Formula inicial:

        viviendas de localidad
        ----------------------- * total de servicios
          viviendas totales

    La suma final se ajusta para que sea exactamente igual
    al total solicitado.
    """

    if total_servicios is None:
        return resultado

    if total_servicios <= 0:
        raise ValueError(
            "El total de servicios debe ser mayor que cero."
        )

    resultado = resultado.copy()

    total_viviendas = (
        resultado["viviendas_habitadas"].sum()
    )

    if total_viviendas <= 0:
        raise ValueError(
            "No se pueden asignar servicios porque no "
            "existen viviendas validas."
        )

    # Calculo proporcional sin redondear.
    resultado["_servicios_exactos"] = (
        resultado["viviendas_habitadas"]
        / total_viviendas
        * total_servicios
    )

    # Asignacion inicial usando la parte entera.
    resultado["servicios_propuestos"] = (
        resultado["_servicios_exactos"]
        .astype(int)
    )

    # Se calcula cuantos servicios faltan por distribuir.
    servicios_asignados = (
        resultado["servicios_propuestos"].sum()
    )

    servicios_faltantes = (
        total_servicios - servicios_asignados
    )

    # Parte decimal de cada calculo.
    resultado["_residuo"] = (
        resultado["_servicios_exactos"]
        - resultado["servicios_propuestos"]
    )

    if servicios_faltantes > 0:
        # Los servicios restantes se entregan a las
        # localidades con mayor parte decimal.
        indices = (
            resultado["_residuo"]
            .sort_values(ascending=False)
            .head(servicios_faltantes)
            .index
        )

        resultado.loc[
            indices,
            "servicios_propuestos"
        ] += 1

    # Eliminar columnas auxiliares.
    resultado.drop(
        columns=[
            "_servicios_exactos",
            "_residuo"
        ],
        inplace=True
    )

    return resultado


# ==========================================================
# MOSTRAR RESULTADOS
# ==========================================================

def mostrar_resultados(resultado):
    """
    Muestra el resumen de las localidades agrupadas.
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

    print(
        f"AGEB agrupadas: "
        f"{resultado['cantidad_ageb'].sum():,.0f}"
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
        "clave_localidad",
        "nombre_localidad",
        "cantidad_ageb",
        "poblacion_total",
        "viviendas_habitadas",
        "grado_rezago_representativo",
        "factor_socioeconomico"
    ]

    if "servicios_propuestos" in resultado.columns:
        columnas_muestra.append(
            "servicios_propuestos"
        )

    print("\nPrimeras 20 localidades:")
    print("-" * 70)

    print(
        resultado[columnas_muestra]
        .head(20)
        .to_string(index=False)
    )

    if "servicios_propuestos" in resultado.columns:
        print(
            "\nTotal de servicios propuestos: "
            f"{resultado['servicios_propuestos'].sum():,}"
        )


# ==========================================================
# GUARDAR RESULTADO
# ==========================================================

def guardar_resultados(resultado):
    """
    Guarda el resultado con una fila por localidad.
    """

    # Asegura que la carpeta exista.
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
    Ejecuta el proceso completo.
    """

    # 1. Cargar el CSV con las AGEB de Toluca.
    datos = cargar_datos()

    # 2. Validar las columnas.
    validar_columnas(datos)

    # 3. Limpiar los datos.
    datos = limpiar_datos(datos)

    # 4. Agrupar las AGEB por localidad.
    resultado = agrupar_localidades(datos)

    # 5. Distribuir los servicios proporcionalmente.
    resultado = asignar_servicios_proporcionales(
        resultado,
        TOTAL_SERVICIOS_RAMIRO
    )

    # 6. Mostrar un resumen.
    mostrar_resultados(resultado)

    # 7. Guardar el resultado.
    guardar_resultados(resultado)


# Esta parte es indispensable para ejecutar main()
# al presionar Run en Visual Studio Code.
if __name__ == "__main__":
    main()