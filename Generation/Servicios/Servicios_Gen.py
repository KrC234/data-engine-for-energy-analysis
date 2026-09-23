
import json
import random 

# Leer 
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

# Uso de archivos JSON cómo simulación de registros por parte de las bases de datos.
zonas = readJSON("Test/Testing_data/Zona.json")
tarifas = readJSON("Test/Testing_data/Tarifas.json")
servicios = readJSON("Test/Testing_data/Tipo_servicio.json")

#  Carga de conjunto de reglas en formato JSON para definir el comportamiento del generador
configuracion = readJSON("Test/Rules/Services_Rules.json")


def generar_Servicios(n_servicios):
    
    padron = configuracion.get("padron_global", configuracion) if isinstance(configuracion, dict) else configuracion
    caracter_zona_rules = configuracion.get("caracter_zona", {}) if isinstance(configuracion, dict) else {}
    
    categorias = list(padron.keys())
    pesos_padron = list(padron.values())
    categorias_asignadas = random.choices(categorias, weights=pesos_padron, k=n_servicios)
    
    servicios_generados = []
    
    for idx, categoria_target in enumerate(categorias_asignadas, start=1):
        # Normalizar la categoría objetivo
        cat_target_clean = str(categoria_target).strip().lower()
        
        # Seleccionar zona
        zona_elegida = random.choice(zonas)
        caracter_urbano = zona_elegida.get("caracter_urbano")
        
        # Regla de zona y exclusiones
        regla_zona = caracter_zona_rules.get(caracter_urbano, {})
        excluidos = regla_zona.get("excluidos", [])
        
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
        registro = {
            "id_servicio": idx,
            "id_zona": zona_elegida.get("id"),
            "nombre_zona": zona_elegida.get("nombre"),
            "caracter_urbano": caracter_urbano,
            "clave_servicio": servicio_elegido.get("clave"),
            "nombre_servicio": servicio_elegido.get("nombre"),
            "categoria": servicio_elegido.get("categoria"),
            "clave_tarifa": tarifa_elegida.get("codigo") if tarifa_elegida else None,
            "nombre_tarifa": tarifa_elegida.get("descripcion") if tarifa_elegida else None
        }
        
        servicios_generados.append(registro)
        
    return servicios_generados
