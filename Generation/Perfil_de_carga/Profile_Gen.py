import numpy as np
import json

# Cargar archivos de datos estaticos para la simulación de comportamiento
def readJSON(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    except FileNotFoundError as e:
        print(f"Error al cargar archivos: {e}")
        exit()

# Parametros de Inicio 
horas_array = np.arange(24)   
reglas = readJSON("Rules/Rules.json")
servicios = readJSON("Test/Testing_data/Tipo_servicio.json");

# Funciones matemáticas
def generar_curva_gaussiana(horas, centro, ancho, base, amplitud):
    # Definir un comportamiento de distribución Gaussiano
    return base + amplitud * np.exp(-((horas - centro) ** 2) / (2 * ancho**2))

def normalizar_24(curva):
    # Evitar división por cero en casos donde la curva sea completamente plana y en 0
    suma = np.sum(curva)
    if suma == 0:
        return np.zeros_like(curva)
    factores = (curva / suma) * 24.0
    return np.round(factores, 4)

# Inicialización de iteraciones
def generacion():
    registros = []
    for servicio in servicios["tipos de servicio"]: # Actualizar para ir en armonía con la BD 
        categoria_actual = servicio["categoria"]
        
        # Validar que la categoría exista en las reglas para evitar errores
        if categoria_actual not in reglas["categorias"]:
            continue
            
        reglas_categoria = reglas["categorias"][categoria_actual]
        
        for tipo_dia, modificadores in reglas_categoria["modificadores_dia"].items():
            curva_diaria_acumulada = np.zeros(24)
            
            # Ensamblar las curvas base sumando todas las que pertenezcan a la categoría
            for curva in reglas_categoria["curva_base"]:
                centro_modificado = curva["centro"] + modificadores["desplazamiento_pico_h"]
                amplitud_modificada = curva["amplitud"] * modificadores["factor_amplitud"]
                
                curva_generada = generar_curva_gaussiana(
                    horas=horas_array,
                    centro=centro_modificado,
                    ancho=curva["ancho"],
                    base=curva["base"],
                    amplitud=amplitud_modificada
                )
                curva_diaria_acumulada += curva_generada
                
            # Normalizar para que la suma de factores sea 24.0
            curva_normalizada = normalizar_24(curva_diaria_acumulada)
            
            # Generar los registros individuales para la BD
            for hora in range(24):
                registros.append({
                    "ID": servicio["id_servicio"],
                    "Tipo de día": tipo_dia,
                    "Hora": int(hora),
                    "Factor": float(curva_normalizada[hora])
                })
    return registros

