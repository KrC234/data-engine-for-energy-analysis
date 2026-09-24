import random
import json
import pandas as pd
from datetime import datetime, timedelta

'''
    ASIGNACIÓN DE DISPOSITIVOS  
    Autor: Aalan Kalid Ruíz Colín 
'''

ARCHIVO_SALIDA = "Test/Testting_results/Dispositivos_generados.csv"

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
    dia_aleatorio = random.randint(0, dias_totales)
    return f_inicio + timedelta(days=dia_aleatorio)


# ---------------------------------------------------------------------------------------
# Se definen una serie de reglas para la creación de los modelos
# Entonces, mediante una clave de marca, claves de modelo, y claves de lotes
# Se hace una concatenación la cuál permite establecer el código de serie del dispositivo
# ---------------------------------------------------------------------------------------
def generar_num_serie(prefijo, modelo, lote, secuencial, checksum):
    return f"{prefijo}-{modelo}-{lote}-{secuencial}-{checksum}"

def seleccionar_dispositivo_por_marca(config_marcas, tension_requerida):
    """
    Selecciona aleatoriamente una marca que contenga modelos compatibles
    con el nivel de tensión requerido por el servicio.
    """
    nombres_marcas = list(config_marcas.keys())
    random.shuffle(nombres_marcas)
    
    for nombre_marca in nombres_marcas:
        datos_marca = config_marcas[nombre_marca]
        modelos_tension = datos_marca["modelos_por_tension"].get(tension_requerida, [])
        
        if modelos_tension:
            modelo_elegido = random.choice(modelos_tension)
            lote_elegido = random.choice(datos_marca["lotes"])
            
            return {
                "marca": nombre_marca,
                "prefijo": datos_marca["prefijo"],
                "lote": lote_elegido,
                "modelo": modelo_elegido["modelo"],
                "factor_comunicacion": modelo_elegido["factor_comunicacion"]
            }
            
    # Fallback si ninguna marca tiene esa tensión definida
    return None


def generar_simulacion_marcas(config, servicios):
    
    mapeo_tarifa = config["MAPEO_TARIFA"]
    multiplicadores = config["MULTIPLICADORES"]
    marcas_config = config["marcas"]
    dataset = []

    
    fechas = config["fechas"]
    fecha_inicio = datetime(fechas[0]["año"], fechas[0]["mes"], fechas[0]["dia"])
    fecha_fin = datetime(fechas[1]["año"], fechas[1]["mes"], fechas[1]["dia"])

    # Cada servicio tiene ligado un dispositivo, entonces se recorren cada uno de los servicios, 
    # y se liga consigo un id de dispositivo generado de manera aleatoria respetando su nivel de tensión.
    for i, servicio in enumerate(servicios, start=1):
        id_servicio = servicio.id_servicio
        tarifa = servicio.clave_tarifa
        
        
        # ---------------------------------------------------------------------
        # Para asignar el multiplicador de tensión, se catalogaron las tarifas. 
        # Cada catalogo de tarifa tiene asociado consigo un multiplicador
        # ---------------------------------------------------------------------
        tension = mapeo_tarifa.get(tarifa, "BAJA_TENSION")
        multiplicador = multiplicadores.get(tension, 1.0)
        
        # --------------------------------------------------------------------------------------------------
        # El catalogo de marcas cuenta con una jerarquia basado en el catalogo de tension
        # Entonces basado en el catalogo, se elige uno de los modelos disponibles y se simula la instalación
        # --------------------------------------------------------------------------------------------------
        disp = seleccionar_dispositivo_por_marca(marcas_config, tension)
        
        if disp is None:
            print(f"Advertencia: No se encontró dispositivo para la tensión {tension} en el servicio {id_servicio}")
            continue

        # Se contruye el Número de serie tomando como base los prefijos definidos en el diccionario de datos 
        secuencial = f"{i:06d}"
        checksum = random.randint(0, 9)
        codigo = generar_num_serie(disp["prefijo"], disp["modelo"], disp["lote"], secuencial, checksum)
        fecha_instal = generar_fecha(fecha_inicio, fecha_fin)

        dataset.append({
            "id_dispositivo": i,
            "id_servicio": id_servicio,
            "clave_tarifa": tarifa,
            "numero_de_serie": codigo,
            "marca": disp["marca"],
            "modelo": disp["modelo"],
            "tension": tension,
            "multiplicador": multiplicador,
            "factor_comunicacion": disp["factor_comunicacion"],
            "fecha_instalacion": fecha_instal,
            "fecha_retiro": None
        })

    return dataset


config_dispositivos = readJSON("Rules/Dispositivos.json")

# Genera los registros mapeando desde el generador de tuples
registros_simulados = generar_simulacion_marcas(config_dispositivos,df_servicios)
if __name__ =='__main__':
    datos = registros_simulados
    
    df = pd.DataFrame(datos)
    
    df.to_csv(ARCHIVO_SALIDA, index=False, encoding='utf-8')
    
