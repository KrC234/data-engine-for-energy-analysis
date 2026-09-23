import random
import json
from datetime import datetime, timedelta

def readJSON(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            return data
            
    except FileNotFoundError as e:
        print(f"Error al cargar archivos: {e}")
        exit()
        

def generar_fecha(f_inicio, f_fin):
    diferencia = f_fin - f_inicio
    
    dias_totales = diferencia.days
    
    dia_aleatorio = random.randint(0,dias_totales)
    
    return f_inicio + timedelta(days=dia_aleatorio)

def generar_num_serie(prefijo,modelo,lote,secuencial,checksum):
    return f"{prefijo}-{modelo}-{lote}-{secuencial}-{checksum}"


def generar_simulacion_n_marcas(config, total_registros):
    
    lista_marcas = config["dispositivos"]
    dataset = []

    fechas = config["fechas"]
    
    fecha_inicio = datetime(fechas[0]["año"],fechas[0]["mes"],fechas[0]["dia"])
    fecha_fin = datetime(fechas[1]["año"],fechas[1]["mes"],fechas[1]["dia"])
    
    for i in range(1, total_registros + 1):
        # Selecciona aleatoriamente cualquier elemento dentro del rango total de marcas
        dispositivo_base = random.choice(lista_marcas)
                
        prefijo = dispositivo_base["prefijo"]
        modelo = random.choice(dispositivo_base["modelos"])
        lote = random.choice(dispositivo_base["lotes"])
        secuencial = f"{i:06d}"
        checksum = random.randint(0, 9)
        
        codigo = generar_num_serie(prefijo,modelo,lote,secuencial,checksum)
        fecha_instal = generar_fecha(fecha_inicio,fecha_fin)
        dataset.append({
            "numero de serie": codigo,
            "marca": dispositivo_base["marca"],
            "fecha de instalación": fecha_instal
        })
        
    return dataset

config_dispositivos = readJSON("Generation/Servicios/Dispositivos.json")
# Genera los 1000 registros incluyendo las 3 marcas (o N marcas si agregas más al JSON)
registros_simulados = generar_simulacion_n_marcas(config_dispositivos, 10)

for registro in registros_simulados:
    print(registro)