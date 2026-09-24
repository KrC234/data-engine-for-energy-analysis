"""Generador de perfiles horarios de HyperDataSynthetic.

Genera 72 perfiles por cada tipo de servicio:

    3 tipos de dia x 24 horas = 72 perfiles

Los tipos de servicio se obtienen directamente desde PostgreSQL y no desde
archivos JSON. El modulo no ejecuta ninguna accion al importarse.
"""

from __future__ import annotations

from typing import Any

import numpy as np


# ======================================================================
# CONSTANTES
# ======================================================================

HORAS = np.arange(24, dtype=float)
TIPOS_DIA = ("H", "S", "D")


# Curvas base por categoria.
# Cada tupla contiene: centro, ancho, base y amplitud.
CURVAS_POR_CATEGORIA = {
    "RESIDENCIAL": [
        (7.0, 1.8, 0.18, 0.75),
        (20.0, 2.6, 0.18, 1.60),
    ],
    "COMERCIAL": [
        (11.0, 3.2, 0.10, 1.45),
        (16.0, 2.8, 0.05, 0.85),
    ],
    "PUBLICO": [
        (10.0, 2.8, 0.12, 1.30),
        (15.0, 2.5, 0.08, 0.75),
    ],
    "SERVICIO": [
        (8.0, 3.5, 0.55, 0.55),
        (18.0, 3.5, 0.55, 0.45),
    ],
    "ALUMBRADO": [
        (1.0, 3.0, 0.02, 1.30),
        (22.0, 3.0, 0.02, 1.45),
    ],
    "MOVILIDAD": [
        (8.0, 2.2, 0.42, 0.70),
        (18.0, 2.4, 0.42, 0.78),
    ],
}


# Modificadores aplicados a cada tipo de dia.
# desplazamiento: mueve los picos en horas.
# amplitud: aumenta o reduce la actividad.
MODIFICADORES_DIA = {
    "H": {
        "desplazamiento": 0.0,
        "amplitud": 1.00,
    },
    "S": {
        "desplazamiento": 1.0,
        "amplitud": 0.92,
    },
    "D": {
        "desplazamiento": 1.5,
        "amplitud": 0.82,
    },
}


# Ajustes adicionales por categoria y tipo de dia.
# Permiten, por ejemplo, reducir escuelas y oficinas en domingo/festivo.
FACTORES_CATEGORIA_DIA = {
    "RESIDENCIAL": {"H": 1.00, "S": 1.05, "D": 1.10},
    "COMERCIAL": {"H": 1.00, "S": 0.92, "D": 0.70},
    "PUBLICO": {"H": 1.00, "S": 0.48, "D": 0.22},
    "SERVICIO": {"H": 1.00, "S": 0.98, "D": 0.96},
    "ALUMBRADO": {"H": 1.00, "S": 1.00, "D": 1.00},
    "MOVILIDAD": {"H": 1.00, "S": 0.88, "D": 0.76},
}


# ======================================================================
# FUNCIONES MATEMATICAS
# ======================================================================


def generar_curva_gaussiana(
    horas: np.ndarray,
    centro: float,
    ancho: float,
    base: float,
    amplitud: float,
) -> np.ndarray:
    """Genera una curva gaussiana sobre las horas recibidas."""
    if ancho <= 0:
        raise ValueError("El ancho de una curva debe ser mayor que cero")

    return base + amplitud * np.exp(
        -((horas - centro) ** 2) / (2 * ancho**2)
    )


def normalizar_24(curva: np.ndarray) -> np.ndarray:
    """Normaliza una curva para que la suma de sus 24 factores sea 24."""
    suma = float(np.sum(curva))

    if suma <= 0:
        raise ValueError("No se puede normalizar una curva con suma cero")

    factores = (curva / suma) * 24.0
    factores = np.round(factores, 4)

    # Corrige el pequeÃ±o error producido por el redondeo para mantener
    # exactamente una suma de 24.0000.
    diferencia = round(24.0 - float(np.sum(factores)), 4)
    indice_maximo = int(np.argmax(factores))
    factores[indice_maximo] = round(
        float(factores[indice_maximo]) + diferencia,
        4,
    )

    return factores


# ======================================================================
# CONSULTAS
# ======================================================================


def cargar_tipos_servicio(connection: Any) -> list[dict[str, Any]]:
    """Obtiene los tipos de servicio directamente desde PostgreSQL."""
    sql = """
        SELECT
            id_tipo_servicio,
            clave,
            categoria
        FROM energia.tipo_servicio
        ORDER BY id_tipo_servicio
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        filas = cursor.fetchall()

    if not filas:
        raise RuntimeError(
            "energia.tipo_servicio esta vacia. "
            "Ejecuta database/sql/02_catalogos.sql primero."
        )

    servicios = []

    for id_tipo_servicio, clave, categoria in filas:
        categoria_normalizada = str(categoria).upper()

        if categoria_normalizada not in CURVAS_POR_CATEGORIA:
            raise ValueError(
                f"La categoria {categoria_normalizada!r} del tipo "
                f"{clave!r} no tiene una curva configurada"
            )

        servicios.append(
            {
                "id_tipo_servicio": int(id_tipo_servicio),
                "clave": clave,
                "categoria": categoria_normalizada,
            }
        )

    return servicios


# ======================================================================
# GENERACION
# ======================================================================


def construir_perfiles(
    tipos_servicio: list[dict[str, Any]],
) -> list[tuple[int, str, int, float]]:
    """Construye todos los perfiles sin insertarlos todavÃ­a."""
    registros: list[tuple[int, str, int, float]] = []

    for servicio in tipos_servicio:
        id_tipo_servicio = servicio["id_tipo_servicio"]
        categoria = servicio["categoria"]
        curvas_categoria = CURVAS_POR_CATEGORIA[categoria]

        for tipo_dia in TIPOS_DIA:
            modificador = MODIFICADORES_DIA[tipo_dia]
            factor_categoria = FACTORES_CATEGORIA_DIA[categoria][tipo_dia]
            curva_acumulada = np.zeros(24, dtype=float)

            for centro, ancho, base, amplitud in curvas_categoria:
                centro_modificado = centro + modificador["desplazamiento"]
                amplitud_modificada = (
                    amplitud
                    * modificador["amplitud"]
                    * factor_categoria
                )

                curva_acumulada += generar_curva_gaussiana(
                    horas=HORAS,
                    centro=centro_modificado,
                    ancho=ancho,
                    base=base,
                    amplitud=amplitud_modificada,
                )

            curva_normalizada = normalizar_24(curva_acumulada)

            for hora, factor in enumerate(curva_normalizada):
                factor_final = float(factor)

                if not 0 <= factor_final <= 6:
                    raise ValueError(
                        "Factor fuera del rango permitido por PostgreSQL: "
                        f"tipo={id_tipo_servicio}, dia={tipo_dia}, "
                        f"hora={hora}, factor={factor_final}"
                    )

                registros.append(
                    (
                        id_tipo_servicio,
                        tipo_dia,
                        hora,
                        factor_final,
                    )
                )

    return registros


def generar_perfiles(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    """Genera e inserta los perfiles horarios en PostgreSQL.

    Usa ON CONFLICT para actualizar perfiles existentes. Por eso puede
    ejecutarse varias veces sin duplicar la llave primaria.
    """
    del config
    del rules

    tipos_servicio = cargar_tipos_servicio(connection)
    registros = construir_perfiles(tipos_servicio)

    sql = """
        INSERT INTO energia.perfil_carga_horaria (
            id_tipo_servicio,
            tipo_dia,
            hora,
            factor
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id_tipo_servicio, tipo_dia, hora)
        DO UPDATE SET
            factor = EXCLUDED.factor
    """

    try:
        with connection.cursor() as cursor:
            cursor.executemany(sql, registros)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    esperados = len(tipos_servicio) * 3 * 24

    if len(registros) != esperados:
        raise RuntimeError(
            f"Se generaron {len(registros)} perfiles, "
            f"pero se esperaban {esperados}"
        )

    print(f"[OK] Tipos de servicio procesados: {len(tipos_servicio):,}")
    print(f"[OK] Perfiles horarios generados: {len(registros):,}")
    print("[OK] Cada curva suma 24.0000")

    return len(registros)


# Alias uniforme para main.py.
def generar(
    connection: Any,
    config: dict[str, Any],
    rules: dict[str, Any],
) -> int:
    return generar_perfiles(connection, config, rules)


if __name__ == "__main__":
    print(
        "Este archivo forma parte del proyecto. "
        "Ejecuta python main.py desde la raiz."
    )