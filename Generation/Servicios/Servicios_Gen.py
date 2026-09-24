import json
import random 
import pandas as pd 



# Leer archivos JSON (de registro y de configuración) 
def readJSON(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Si el JSON es un diccionario del tipo {"nombre": [{}, {}, ...]}
            # extraemos directamente el valor de la primera clave existente.
            if isinstance(data, dict) and len(data) > 0:
                first_value = next(iter(data.values()))
                if isinstance(first_value, list):
                    return first_value
            
            return data
            
    except FileNotFoundError as e:
        print(f"Error al cargar archivos: {e}")
        exit()



# Carga unificada de datos 


# --------------------------------------------------------------------------------------------
# Los archivos JSON se usan para realizar una serie de pruebas 
# Estos actuan como una simulación de los registros de la bd
# Permiten extraer los ID's y categorías necesarias para simular las relaciones entre tablas
# --------------------------------------------------------------------------------------------
zonas = readJSON("Test/Testing_data/Zona.json")
tarifas = readJSON("Test/Testing_data/Tarifas.json")
servicios = readJSON("Test/Testing_data/Tipo_servicio.json")

#  Carga del conjunto de reglas base 
configuracion = readJSON("Test/Rules/Services_Rules.json")

ARCHIVO_SALIDA = "Test/Testing_data/Servicios_generados.csv"

def generar_Servicios(n_servicios):
    
    # ----------------------------------------------------
    # El conjunto de reglas define un padron electoral, el cual define la distribución de servicios en la ciudad
    # El caracter de la zona ayuda a modelar los posibles servicios a los que tiene acceso la zona
    # Ejm: Una zona de caracter popular dificilmente tendra servicios de consumo alto y contara con mayores negocios locales
    # Por otro lado una zona de caracter residencial Alto, dificilmente tendra servicios de consumo para viviendas sociales
    #
    
    padron = configuracion.get("padron_global", configuracion) if isinstance(configuracion, dict) else configuracion
    caracter_zona_rules = configuracion.get("caracter_zona", {}) if isinstance(configuracion, dict) else {}
    
    categorias = list(padron.keys())
    pesos_padron = list(padron.values())
    
    # Una vez que se obtiene el caracter de la zona, se le asigna el peso de probabilidad
    categorias_asignadas = random.choices(categorias, weights=pesos_padron, k=n_servicios)
    
    servicios_generados = []
    
    for idx, categoria_target in enumerate(categorias_asignadas, start=1):
        # Normalizar la categoría objetivo
        cat_target_clean = str(categoria_target).strip().lower()
        
        # Seleccionar zona
        zona_elegida = random.choice(zonas)
        caracter_urbano = zona_elegida.get("caracter_urbano")
        
        # Regla de zona y exclusiones
        #TODO: en este momento las exclusiones sirven para modelar el tipo de servicios esperados por el caracter de cada zona.
        #TODO: las reglas de modelado pueden y deberan adaptarse para futuras versiones
        regla_zona = caracter_zona_rules.get(caracter_urbano, {})
        excluidos = regla_zona.get("excluidos", [])
        
        
        # ----------------------------------
        # La categoría de servicio es el indice principal dado que es la que establece la relación entre el servicio, tipo de servicio y caracter de la zona
        #-----------------------------------
        
        # Filtrar candidatos
        candidatos_servicio = [
            s for s in servicios 
            if str(s.get("categoria", "")).strip().lower() == cat_target_clean
            and s.get("id_servicio") not in excluidos
        ]
        
        # Si no hay por categoría, intentar por ID
        if not candidatos_servicio:
            candidatos_servicio = [
                s for s in servicios 
                if str(s.get("id_servicio", "")).strip().lower() == cat_target_clean
            ]

        # Fallback 2: Usar catálogo completo si no hay coincidencia
        if not candidatos_servicio:
            candidatos_servicio = servicios

        servicio_elegido = random.choice(candidatos_servicio)
        
        # Filtrar tarifas compatibles
        cat_servicio_clean = str(servicio_elegido.get("categoria", "")).strip().lower()
        
        tarifas_compatibles = [
            t for t in tarifas 
            if isinstance(t, dict) and str(t.get("categoria", "")).strip().lower() == cat_servicio_clean
        ]
        
        tarifa_elegida = random.choice(tarifas_compatibles) if tarifas_compatibles else None
        
        # Estructura de salida (hasta el momento)
        #TODO: Se solicita igual agregar registros de: Clave de servicio (12 digitos), Referencia(Dirección),Ocupación,Carga Contrada(Kw), y si cuentan con un panel solar
        # * Será necesario definir las reglas para la asignación de estos datos faltantes 
        registro = {
            "id_servicio": idx,
            "id_zona": zona_elegida.get("id"),
            "clave_servicio": servicio_elegido.get("clave"),
            "tipode_de_servicio": servicio_elegido.get("nombre"),
            "categoria": servicio_elegido.get("categoria"),
            "clave_tarifa": tarifa_elegida.get("codigo") if tarifa_elegida else None,
            "tipo_de_tarifa": tarifa_elegida.get("descripcion") if tarifa_elegida else None
        }
        
        servicios_generados.append(registro)
        
    return servicios_generados
# Para poder analizar el comportamiento de la asignación, se genera un archivo CSV para poder analizar si se está logrando el comportamiento esperado 
if __name__ =='__main__':
    datos = generar_Servicios(15)
    
    df = pd.DataFrame(datos)
    
    df.to_csv(ARCHIVO_SALIDA, index=False, encoding='utf-8')
    