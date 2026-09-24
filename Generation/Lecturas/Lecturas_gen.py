"""
Simulador de lecturas de medidores de energía eléctrica
========================================================

Genera, para cada dispositivo (medidor) y para cada uno de los días definidos
en `Dias.json`, los 24 registros horarios de lectura acumulada, a partir del
modelo:

    consumo_real(m, t) =
          B(tipo_servicio)                     # nivel base del tipo de punto de consumo
        x P(tipo_servicio, tipo_dia, hora)      # perfil de carga horaria (curva de carga)
        x Fz(zona)                              # factor socioeconómico de la zona
        x Fe(temperatura_media_del_dia)         # factor estacional
        x (1 + e),   e ~ Normal(0, sigma_tipo) truncado

Reglas de negocio implementadas
--------------------------------
1. Cada medidor arranca en 0 y NUNCA se reinicia entre días: la lectura es un
   registro acumulado y creciente a lo largo de toda la simulación.
2. El consumo de cada hora se obtiene como la diferencia entre la lectura
   final y la lectura inicial de esa hora (es decir, el incremento horario
   que se le suma al acumulado).
3. El "perfil de carga" (curva horaria) depende del tipo de servicio Y del
   tipo de día (Habil / Inhabil / Festivo), tal como está modelado en
   `perfiles_carga.csv`.
4. Un dispositivo sólo genera lecturas en los días en que está en operación,
   de acuerdo con su `fecha_instalacion` y su `fecha_retiro` (si existe). Si
   el medidor todavía no existía o ya fue retirado, simplemente no se generan
   filas para ese día (el acumulado se mantiene congelado, no se resetea).
5. El factor estacional Fe se modela como una función lineal de la
   temperatura media del día respecto de una temperatura de referencia
   "neutra" (parametrizable), ponderada por la sensibilidad a la temperatura
   propia de cada tipo de servicio:

        Fe(temp) = 1 + sensibilidad_temperatura * (temp_media - temp_referencia)

   Este es un supuesto de modelado razonable (no viene dado explícitamente en
   los catálogos), y se deja como parámetro configurable (--temp-referencia).
6. El multiplicador del dispositivo (relación de transformación del medidor,
   p. ej. medidores en media tensión con TC/TP) se aplica dividiendo el
   consumo real entre el multiplicador para obtener el incremento que se
   suma al registro del medidor. Así, el consumo real siempre se puede
   recuperar como: (lectura_final - lectura_inicial) x multiplicador.

Archivos de entrada esperados (formato "tablas de base de datos")
-------------------------------------------------------------------
- Dispositivos_generados.csv : catálogo de medidores (1 medidor por servicio)
- Servicios_generados.csv    : catálogo de servicios (zona, tipo de servicio, tarifa)
- perfiles_carga.csv         : curva de carga horaria por tipo de servicio y tipo de día
- Dias.json                  : calendario de simulación (tipo de día y temperaturas)
- Tipo_servicio.json         : catálogo de tipos de servicio (B, dispersión, sensibilidad)
- Zona.json                  : catálogo de zonas (factor socioeconómico)
- Tarifas.json               : catálogo de tarifas (sólo se usa como referencia/trazabilidad)

Salida
------
Un CSV (`lecturas_generadas.csv` por defecto) con 24 registros por
dispositivo y por día, con las columnas:

    id_dispositivo, id_servicio, numero_de_serie, fecha, hora, timestamp,
    tipo_dia, lectura_acumulada_kwh, consumo_incremental_kwh, consumo_real_kwh

Uso
---
    python simulador_lecturas.py --input-dir ./datos --output lecturas_generadas.csv --seed 42
"""

import argparse
import csv
import json
import random
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Utilidades de carga de datos
# ---------------------------------------------------------------------------

def load_csv(path: Path) -> list[dict]:
    """Carga un CSV como lista de diccionarios (maneja BOM y CRLF)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_date(value):
    """Convierte 'YYYY-MM-DD' a date; devuelve None si viene vacío."""
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# Variable aleatoria normal truncada (rechazo simple, sin dependencias extra)
# ---------------------------------------------------------------------------

def truncated_normal(mu: float, sigma: float, low: float, high: float, max_tries: int = 200) -> float:
    """Muestra e ~ Normal(mu, sigma) truncada al intervalo [low, high].

    Si sigma es 0 (o casi), regresa mu directamente. Si tras max_tries
    intentos no se obtiene un valor dentro del rango, se recorta (clip) el
    último valor muestreado como salvaguarda numérica.
    """
    if sigma <= 0:
        return min(max(mu, low), high)
    for _ in range(max_tries):
        e = random.gauss(mu, sigma)
        if low <= e <= high:
            return e
    return min(max(e, low), high)


# ---------------------------------------------------------------------------
# Carga e indexación de catálogos
# ---------------------------------------------------------------------------

def build_indices(input_dir: Path):
    dispositivos = load_csv(input_dir / "Dispositivos_generados.csv")
    servicios = load_csv(input_dir / "Servicios_generados.csv")
    perfiles = load_csv(input_dir / "perfiles_carga.csv")
    dias = load_json(input_dir / "Dias.json")["dias"]
    tipos_servicio = load_json(input_dir / "Tipo_servicio.json")["tipos de servicio"]
    zonas = load_json(input_dir / "Zona.json")["zona"]
    tarifas = load_json(input_dir / "Tarifas.json")["tarifas"]

    servicios_by_id = {int(s["id_servicio"]): s for s in servicios}
    zonas_by_id = {int(z["id"]): z for z in zonas}
    tipo_serv_by_clave = {t["clave"]: t for t in tipos_servicio}
    tarifas_by_codigo = {t["codigo"]: t for t in tarifas}  # trazabilidad, no entra en la fórmula

    # perfil_map[(id_tipo_servicio, tipo_dia, hora)] = factor de carga
    perfil_map = {}
    for row in perfiles:
        key = (int(row["ID"]), row["Tipo de día"], int(row["Hora"]))
        perfil_map[key] = float(row["Factor"])

    # normalizar dispositivos
    dev_records = []
    for d in dispositivos:
        dev_records.append({
            "id_dispositivo": int(d["id_dispositivo"]),
            "id_servicio": int(d["id_servicio"]),
            "numero_de_serie": d["numero_de_serie"],
            "multiplicador": float(d["multiplicador"]) if d.get("multiplicador") else 1.0,
            "fecha_instalacion": parse_date(d.get("fecha_instalacion")),
            "fecha_retiro": parse_date(d.get("fecha_retiro")),
        })

    dias_ordenados = sorted(dias, key=lambda d: d["fecha"])

    return {
        "dev_records": dev_records,
        "servicios_by_id": servicios_by_id,
        "zonas_by_id": zonas_by_id,
        "tipo_serv_by_clave": tipo_serv_by_clave,
        "tarifas_by_codigo": tarifas_by_codigo,
        "perfil_map": perfil_map,
        "dias_ordenados": dias_ordenados,
    }


# ---------------------------------------------------------------------------
# Motor de simulación
# ---------------------------------------------------------------------------

def simular(idx: dict, temp_referencia: float, e_min: float, e_max: float) -> list[dict]:
    dev_records = idx["dev_records"]
    servicios_by_id = idx["servicios_by_id"]
    zonas_by_id = idx["zonas_by_id"]
    tipo_serv_by_clave = idx["tipo_serv_by_clave"]
    perfil_map = idx["perfil_map"]
    dias_ordenados = idx["dias_ordenados"]

    # Lectura acumulada por medidor: arranca en 0 y NUNCA se reinicia.
    lector_acumulado = {d["id_dispositivo"]: 0.0 for d in dev_records}

    filas = []

    for dia in dias_ordenados:
        fecha = parse_date(dia["fecha"])
        tipo_dia = dia["tipo_dia"]
        temp_media = dia["temperatura_media"]

        for dev in dev_records:
            # ¿El medidor está en operación este día?
            if dev["fecha_instalacion"] and fecha < dev["fecha_instalacion"]:
                continue
            if dev["fecha_retiro"] and fecha > dev["fecha_retiro"]:
                continue

            servicio = servicios_by_id.get(dev["id_servicio"])
            if servicio is None:
                continue

            tipo_serv = tipo_serv_by_clave.get(servicio["clave_servicio"])
            if tipo_serv is None:
                continue

            zona = zonas_by_id.get(int(servicio["id_zona"]))
            fz = zona["factor_socioeconomico"] if zona else 1.0

            b = tipo_serv["consumo_base_kwh_h"]
            sigma = tipo_serv["dispersion"]
            sens = tipo_serv["sensibilidad_temperatura"]
            id_perfil = tipo_serv["id_servicio"]  # el perfil de carga se indexa por tipo de servicio

            # Factor estacional: crece/decrece linealmente respecto de una
            # temperatura de referencia "neutra", según la sensibilidad del
            # tipo de servicio. Se acota para evitar valores absurdos o negativos.
            fe = 1 + sens * (temp_media - temp_referencia)
            fe = max(fe, 0.05)

            multiplicador = dev["multiplicador"] or 1.0

            for hora in range(24):
                p = perfil_map.get((id_perfil, tipo_dia, hora), 0.0)

                e = truncated_normal(0.0, sigma, e_min, e_max)
                consumo_real = b * p * fz * fe * (1 + e)
                consumo_real = max(consumo_real, 0.0)  # el consumo nunca es negativo

                # Lo que efectivamente "gira" el disco/registro del medidor
                # (antes de aplicar la relación de transformación).
                incremento_registro = consumo_real / multiplicador if multiplicador else consumo_real
                lector_acumulado[dev["id_dispositivo"]] += incremento_registro

                filas.append({
                    "id_dispositivo": dev["id_dispositivo"],
                    "id_servicio": dev["id_servicio"],
                    "numero_de_serie": dev["numero_de_serie"],
                    "fecha": dia["fecha"],
                    "hora": hora,
                    "timestamp": f"{dia['fecha']} {hora:02d}:00:00",
                    "tipo_dia": tipo_dia,
                    "lectura_acumulada_kwh": round(lector_acumulado[dev["id_dispositivo"]], 4),
                    "consumo_incremental_kwh": round(incremento_registro, 4),
                    "consumo_real_kwh": round(consumo_real, 4),
                })

    return filas


# ---------------------------------------------------------------------------
# Escritura de resultados
# ---------------------------------------------------------------------------

def escribir_csv(filas: list[dict], output_path: Path) -> None:
    fieldnames = [
        "id_dispositivo", "id_servicio", "numero_de_serie", "fecha", "hora",
        "timestamp", "tipo_dia", "lectura_acumulada_kwh",
        "consumo_incremental_kwh", "consumo_real_kwh",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(filas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Simulador de lecturas de medidores de energía.")
    parser.add_argument("--input-dir", default=".", help="Carpeta con los archivos de catálogo (CSV/JSON).")
    parser.add_argument("--output", default="lecturas_generadas.csv", help="Ruta del CSV de salida.")
    parser.add_argument("--seed", type=int, default=42, help="Semilla para reproducibilidad del ruido aleatorio.")
    parser.add_argument("--temp-referencia", type=float, default=18.0,
                         help="Temperatura (°C) de referencia 'neutra' para el factor estacional Fe.")
    parser.add_argument("--e-min", type=float, default=-0.9,
                         help="Cota inferior del ruido truncado e (evita factores negativos).")
    parser.add_argument("--e-max", type=float, default=1.5,
                         help="Cota superior del ruido truncado e.")
    args = parser.parse_args()

    random.seed(args.seed)

    input_dir = Path(args.input_dir)
    idx = build_indices(input_dir)
    filas = simular(idx, args.temp_referencia, args.e_min, args.e_max)

    output_path = Path(args.output)
    escribir_csv(filas, output_path)

    n_dispositivos = len(idx["dev_records"])
    n_dias = len(idx["dias_ordenados"])
    print(f"Dispositivos procesados : {n_dispositivos}")
    print(f"Días simulados          : {n_dias}")
    print(f"Registros generados     : {len(filas)}")
    print(f"Archivo de salida       : {output_path.resolve()}")


if __name__ == "__main__":
    main()
