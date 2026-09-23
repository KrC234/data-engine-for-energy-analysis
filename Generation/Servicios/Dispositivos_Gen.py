import random
import json
import pandas as pd
from datetime import datetime, timedelta
'''
    ASIGNACIÓN DE DISPOSITIVOS  
    Autor: Aalan Kalid Ruíz Colín 
'''
def readJSON(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            return data
            
    except FileNotFoundError as e:
        print(f"Error al cargar archivos: {e}")
        exit()
        

df_servicios = pd.read_csv("Test/Testing_data/Servicios_generados.csv")

# ------------------------------------------------------------------------------------------------------
# Para definir las fechas, se proponen dos fechas, una de inicio y una final. 
# Se saca la diferencia de días entre esas fechas, y de manera aleatoria se selecciona un número de días
# Este número de días sumados a la fecha de inicio determinan una fecha dentro del rango
# ------------------------------------------------------------------------------------------------------
def generar_fecha(f_inicio, f_fin):
    diferencia = f_fin - f_inicio
    
    dias_totales = diferencia.days
    
    dia_aleatorio = random.randint(0,dias_totales)
    
    return f_inicio + timedelta(days=dia_aleatorio)

# ---------------------------------------------------------------------------------------
# Se definen una serie de reglas para la creación de los modelos
# Entonces, mediante una clave de marca, claves de modelo, y claves de lotes
# Se hace una concatenación la cuál permite establecer el código de serie del dispositivo
# ---------------------------------------------------------------------------------------
def generar_num_serie(prefijo,modelo,lote,secuencial,checksum):
    return f"{prefijo}-{modelo}-{lote}-{secuencial}-{checksum}"


def generar_simulacion_n_marcas(config, servicios):
    
    lista_marcas = config["dispositivos"]
    dataset = []

    fechas = config["fechas"]
    
    fecha_inicio = datetime(fechas[0]["año"],fechas[0]["mes"],fechas[0]["dia"])
    fecha_fin = datetime(fechas[1]["año"],fechas[1]["mes"],fechas[1]["dia"])
    i = 0
    #TODO: De momento este modulo contempla unicamente la instalación de dispositivos, en su defecto habra que re plantear el modulo para la simulación de los cambios de dispositivos
    # Cada servicio tiene ligado un dispositivo, entonces se recorren cada uno de los servicios, y se liga consigo un id de dispositivo generado de manera aleatoria. 
    for servicio in servicios:
        i=i+1
        id_servicio = servicio.id_servicio
        dispositivo_base = random.choice(lista_marcas)
                
        prefijo = dispositivo_base["prefijo"]
        modelo = random.choice(dispositivo_base["modelos"])
        lote = random.choice(dispositivo_base["lotes"])
        secuencial = f"{i:06d}"
        checksum = random.randint(0, 9)
        
        codigo = generar_num_serie(prefijo,modelo,lote,secuencial,checksum)
        fecha_instal = generar_fecha(fecha_inicio,fecha_fin)
        
        #! Aún queda pendiente llevar a cabo la asignación de el multiplicador, y de la calidad de enlace
        # ------------------------------------------------------------------------------------------------
        # Los factores de calidad de enlace y del multiplicador son vitales para la simulación de lecturas
        # Debera de plantearse el conjunto de reglas para validar estos valores
        # ------------------------------------------------------------------------------------------------
        dataset.append({
            "id_dispositivo": i,
            "id_servicio": id_servicio,
            "numero de serie": codigo,
            "marca": dispositivo_base["marca"],
            "fecha de instalación": fecha_instal,
            "fecha de retiro": None
        })
        
    return dataset

config_dispositivos = readJSON("Rules/Dispositivos.json")

# Genera los 1000 registros incluyendo las 3 marcas (o N marcas si agregas más al JSON)
registros_simulados = generar_simulacion_n_marcas(config_dispositivos, df_servicios.itertuples())

for registro in registros_simulados:
    print(registro)