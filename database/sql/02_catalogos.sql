-- ============================================================
-- 02_catalogos.sql
-- HyperDataSynthetic - Caso de estudio: municipio de Toluca
--
-- Requisitos:
--   1) Ejecutar conectado a energia_hsd.
--   2) Ejecutar despues de 01_esquema.sql.
--
-- Este script puede reejecutarse mientras aun no existan servicios, medidores
-- ni hechos. Si ya existe padron, se detiene para proteger la integridad.
-- Los nombres, poblacion, viviendas, rezago y factor socioeconomico
-- proceden del insumo territorial agregado del proyecto.
--
-- IMPORTANTE SOBRE superficie_km2:
--   Son estimaciones HSD no oficiales, calculadas proporcionalmente con
--   viviendas habitadas para completar el modelo sin valores NULL.
--   Deben reemplazarse si posteriormente se calculan areas con cartografia.
-- ============================================================

BEGIN;
SET search_path TO energia;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM servicio LIMIT 1)
       OR EXISTS (SELECT 1 FROM medidor LIMIT 1)
       OR EXISTS (SELECT 1 FROM evento LIMIT 1)
       OR EXISTS (SELECT 1 FROM lectura LIMIT 1)
       OR EXISTS (SELECT 1 FROM alerta LIMIT 1)
       OR EXISTS (SELECT 1 FROM periodo_facturacion LIMIT 1)
    THEN
        RAISE EXCEPTION
            '02_catalogos.sql no puede reinicializar catalogos: ya existe padron o informacion de hechos.';
    END IF;
END $$;

TRUNCATE TABLE perfil_carga_horaria;
TRUNCATE TABLE tipo_evento;
TRUNCATE TABLE tipo_servicio;
TRUNCATE TABLE tarifa;
TRUNCATE TABLE zona;

-- ============================================================
-- 0. AJUSTE DE TRAZABILIDAD TERRITORIAL
-- ============================================================
ALTER TABLE zona
    ADD COLUMN IF NOT EXISTS poblacion_total INTEGER,
    ADD COLUMN IF NOT EXISTS viviendas_habitadas INTEGER,
    ADD COLUMN IF NOT EXISTS grado_rezago_representativo VARCHAR(12),
    ADD COLUMN IF NOT EXISTS id_referencia INTEGER;

ALTER TABLE zona
    ALTER COLUMN superficie_km2 SET NOT NULL;

ALTER TABLE zona DROP CONSTRAINT IF EXISTS ck_zona_poblacion;
ALTER TABLE zona ADD CONSTRAINT ck_zona_poblacion
    CHECK (poblacion_total IS NULL OR poblacion_total >= 0);

ALTER TABLE zona DROP CONSTRAINT IF EXISTS ck_zona_viviendas;
ALTER TABLE zona ADD CONSTRAINT ck_zona_viviendas
    CHECK (viviendas_habitadas IS NULL OR viviendas_habitadas >= 0);

ALTER TABLE zona DROP CONSTRAINT IF EXISTS ck_zona_rezago;
ALTER TABLE zona ADD CONSTRAINT ck_zona_rezago
    CHECK (
        grado_rezago_representativo IS NULL OR
        grado_rezago_representativo IN ('Muy bajo','Bajo','Medio','Alto','Muy alto')
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_zona_id_referencia
    ON zona (id_referencia)
    WHERE id_referencia IS NOT NULL;

-- ============================================================
-- 1. ZONAS: 46 LOCALIDADES DE TOLUCA
-- ============================================================
INSERT INTO zona (
    id_zona, nombre, tipo_urbano, superficie_km2,
    factor_socioeconomico, poblacion_total, viviendas_habitadas,
    grado_rezago_representativo, id_referencia
)
VALUES
    (1, 'Toluca de Lerdo', 'CENTRO', 82.492, 1.739, 223876, 65993, 'Bajo', 1),
    (2, 'San Pablo Autopan', 'POPULAR', 13.371, 0.954, 47932, 10700, 'Alto', 2),
    (3, 'San Cristóbal Huichochitlán', 'PERIFERIA', 11.797, 0.875, 42320, 9442, 'Alto', 3),
    (4, 'San Lorenzo Tepaltitlán', 'RESIDENCIAL_MEDIA', 12.249, 1.657, 35292, 9803, 'Bajo', 4),
    (5, 'Santa Ana Tlapaltitlán', 'RESIDENCIAL_MEDIA', 10.414, 1.587, 33089, 8334, 'Bajo', 5),
    (6, 'Crespa Floresta', 'RESIDENCIAL_ALTA', 11.580, 1.781, 32307, 9266, 'Muy bajo', 6),
    (7, 'Santa María Totoltepec', 'RESIDENCIAL_MEDIA', 11.105, 1.720, 31689, 8886, 'Bajo', 7),
    (8, 'Sauces', 'RESIDENCIAL_ALTA', 11.028, 2.000, 27628, 8824, 'Muy bajo', 8),
    (9, 'San Buenaventura', 'RESIDENCIAL_MEDIA', 8.405, 1.569, 26968, 6725, 'Bajo', 9),
    (10, 'San Mateo Otzacatipan', 'MIXTA', 6.605, 1.232, 22574, 5285, 'Alto', 10),
    (11, 'San Mateo Oxtotitlán', 'RESIDENCIAL_MEDIA', 7.789, 1.711, 22500, 6232, 'Bajo', 11),
    (12, 'San Pedro Totoltepec', 'RESIDENCIAL_MEDIA', 7.140, 1.516, 22374, 5713, 'Bajo', 12),
    (13, 'Capultitlán', 'RESIDENCIAL_MEDIA', 6.943, 1.703, 20703, 5555, 'Bajo', 13),
    (14, 'Santiago Tlacotepec', 'MIXTA', 5.581, 1.250, 19744, 4465, 'Medio', 14),
    (15, 'San Andrés Cuexcontitlán', 'PERIFERIA', 4.846, 0.875, 18180, 3877, 'Alto', 15),
    (16, 'Santa Cruz Atzcapotzaltongo', 'RESIDENCIAL_MEDIA', 4.802, 1.616, 13812, 3842, 'Bajo', 16),
    (17, 'Cacalomacán', 'MIXTA', 4.039, 1.490, 13796, 3231, 'Bajo', 17),
    (18, 'Santiago Miltepec', 'RESIDENCIAL_MEDIA', 4.898, 1.554, 13546, 3918, 'Bajo', 18),
    (19, 'San Diego de los Padres Cuexcontitlán', 'PERIFERIA', 3.685, 0.875, 13381, 2948, 'Alto', 19),
    (20, 'San Felipe Tlalmimilolpan', 'RESIDENCIAL_MEDIA', 4.396, 1.652, 13310, 3517, 'Bajo', 20),
    (21, 'Calixtlahuaca', 'MIXTA', 2.842, 1.250, 9396, 2274, 'Medio', 21),
    (22, 'San Juan Tilapa', 'POPULAR', 2.666, 1.189, 9395, 2133, 'Medio', 22),
    (23, 'La Constitución Toltepec', 'PERIFERIA', 2.592, 0.875, 9209, 2074, 'Alto', 23),
    (24, 'El Cerrillo Vista Hermosa', 'MIXTA', 2.763, 1.211, 9118, 2211, 'Medio', 24),
    (25, 'San Nicolás Tolentino', 'PERIFERIA', 2.375, 0.875, 8406, 1900, 'Alto', 25),
    (26, 'San José Guadalupe Otzacatipan', 'PERIFERIA', 2.246, 0.875, 7984, 1797, 'Alto', 26),
    (27, 'San Miguel Totoltepec', 'MIXTA', 2.449, 1.250, 7890, 1959, 'Medio', 27),
    (28, 'Ejido de la Y Sección Siete A Revolución', 'PERIFERIA', 1.880, 0.875, 7016, 1504, 'Alto', 28),
    (29, 'Tlachaloya Segunda Sección', 'PERIFERIA', 1.839, 0.875, 6778, 1471, 'Alto', 29),
    (30, 'Jicaltepec Autopan', 'PERIFERIA', 1.820, 0.875, 6730, 1456, 'Alto', 30),
    (31, 'San Marcos Yachihuacaltepec', 'MIXTA', 1.830, 1.250, 6250, 1464, 'Medio', 31),
    (32, 'Santiago Tlaxomulco', 'MIXTA', 1.899, 1.294, 6178, 1519, 'Medio', 32),
    (33, 'San Antonio Buenavista', 'RESIDENCIAL_MEDIA', 1.691, 1.625, 5758, 1353, 'Bajo', 33),
    (34, 'Jicaltepec Cuexcontitlán', 'PERIFERIA', 1.570, 0.875, 5399, 1256, 'Alto', 34),
    (35, 'Las Misiones [Conjunto Urbano]', 'RESIDENCIAL_ALTA', 2.309, 2.000, 5229, 1847, 'Muy bajo', 35),
    (36, 'Arroyo Vista Hermosa', 'PERIFERIA', 1.365, 0.875, 4721, 1092, 'Alto', 36),
    (37, 'Paseos San Martín [Conjunto Urbano]', 'MIXTA', 1.669, 1.250, 4257, 1335, 'Medio', 37),
    (38, 'Tlachaloya', 'PERIFERIA', 1.098, 0.875, 4215, 878, 'Alto', 38),
    (39, 'Hacienda Santín (Rancho Santín)', 'RESIDENCIAL_ALTA', 1.805, 2.000, 4203, 1444, 'Muy bajo', 39),
    (40, 'Fraccionamiento Real de San Pablo', 'RESIDENCIAL_MEDIA', 1.515, 1.625, 4090, 1212, 'Bajo', 40),
    (41, 'San Cayetano Morelos', 'POPULAR', 1.308, 1.030, 3988, 1046, 'Alto', 41),
    (42, 'Santa Cruz Otzacatipan', 'MIXTA', 1.115, 1.250, 3822, 892, 'Medio', 42),
    (43, 'Fraccionamiento San Diego', 'RESIDENCIAL_MEDIA', 1.399, 1.625, 3746, 1119, 'Bajo', 43),
    (44, 'San Francisco Totoltepec', 'MIXTA', 0.951, 1.250, 3206, 761, 'Medio', 44),
    (45, 'Galaxias Toluca', 'RESIDENCIAL_MEDIA', 1.160, 1.625, 3090, 928, 'Bajo', 45),
    (46, 'La Magdalena Otzacatipan', 'MIXTA', 0.779, 1.250, 2568, 623, 'Medio', 46);

-- ============================================================
-- 2. TARIFAS: 7 CLASIFICACIONES DEL MODELO
-- ============================================================
INSERT INTO tarifa (id_tarifa, codigo, nombre, categoria, limite_dac_kwh_mes)
VALUES
    (1, '1',     'Domestica de consumo basico',       'DOMESTICA',       250),
    (2, '1C',    'Domestica de clima calido',         'DOMESTICA',       850),
    (3, 'DAC',   'Domestica de alto consumo',         'DOMESTICA',       NULL),
    (4, 'PDBT',  'Pequena demanda comercial',         'COMERCIAL',       NULL),
    (5, 'GDBT',  'Gran demanda comercial',            'COMERCIAL',       NULL),
    (6, 'GDMTH', 'Gran demanda en media tension',     'SERVICIO_PUBLICO',NULL),
    (7, 'APBT',  'Alumbrado publico en baja tension', 'ALUMBRADO',       NULL);

-- ============================================================
-- 3. TIPOS DE SERVICIO: 18 CLASES
-- ============================================================
INSERT INTO tipo_servicio (
    id_tipo_servicio, clave, nombre, categoria,
    consumo_base_kwh_h, factor_dispersion, sensibilidad_temp
)
VALUES
    (1,  'VIV_UNIF',   'Vivienda unifamiliar',          'RESIDENCIAL', 0.350, 0.420, 0.045),
    (2,  'VIV_DEPTO',  'Departamento',                  'RESIDENCIAL', 0.240, 0.380, 0.038),
    (3,  'VIV_SOCIAL', 'Vivienda de interes social',    'RESIDENCIAL', 0.190, 0.350, 0.030),
    (4,  'VIV_RESID',  'Vivienda de consumo alto',      'RESIDENCIAL', 0.980, 0.550, 0.075),
    (5,  'COM_LOCAL',  'Local comercial de barrio',     'COMERCIAL',   1.100, 0.480, 0.040),
    (6,  'MERCADO',    'Mercado publico municipal',     'PUBLICO',    18.500, 0.300, 0.055),
    (7,  'ESCUELA',    'Escuela publica',               'PUBLICO',     6.400, 0.280, 0.035),
    (8,  'CLINICA',    'Centro de salud',               'PUBLICO',    22.000, 0.250, 0.050),
    (9,  'HOSPITAL',   'Hospital',                       'PUBLICO',    85.000, 0.200, 0.048),
    (10, 'EDIF_GOB',   'Edificio gubernamental',        'PUBLICO',    14.200, 0.320, 0.060),
    (11, 'BIBLIOTECA', 'Biblioteca publica',            'PUBLICO',     4.100, 0.300, 0.042),
    (12, 'CTRO_CULT',  'Centro cultural',               'PUBLICO',     5.300, 0.300, 0.040),
    (13, 'CTRO_DEP',   'Centro deportivo',              'PUBLICO',    11.800, 0.350, 0.030),
    (14, 'PARQUE',     'Parque publico iluminado',      'PUBLICO',     2.700, 0.250, 0.005),
    (15, 'POZO_AGUA',  'Pozo de agua potable',          'SERVICIO',   42.000, 0.200, 0.010),
    (16, 'BOMBEO',     'Planta de rebombeo',            'SERVICIO',   58.000, 0.180, 0.008),
    (17, 'ALUMB_PUB',  'Circuito de alumbrado publico', 'ALUMBRADO',   9.600, 0.220, 0.000),
    (18, 'SEMAFORO',   'Nodo de semaforizacion',        'MOVILIDAD',   0.420, 0.150, 0.000);

-- ============================================================
-- 4. TIPOS DE EVENTO: 7 ANOMALIAS
-- ============================================================
INSERT INTO tipo_evento (
    id_tipo_evento, clave, nombre, efecto, afecta_acumulado,
    duracion_min_h, duracion_max_h, intensidad_min, intensidad_max,
    tasa_por_medidor_mes, prob_deteccion, regla_deteccion
)
VALUES
    (1, 'PICO_DEMANDA',         'Pico de demanda',                'INCREMENTO',    TRUE,  1,   3, 2.500, 6.000, 0.0600, 0.950, 'UMBRAL_PICO'),
    (2, 'CONSUMO_ANOMALO',      'Consumo anomalo sostenido',      'INCREMENTO',    TRUE, 24, 168, 1.400, 2.200, 0.0400, 0.700, 'DESVIACION_PERSISTENTE'),
    (3, 'MANIPULACION',         'Manipulacion de medidor',        'REDUCCION',     TRUE,168, 720, 0.200, 0.600, 0.0080, 0.350, 'BRECHA_REAL_REPORTADA'),
    (4, 'FALLA_MEDIDOR',        'Falla de medidor',               'CONGELAMIENTO', TRUE, 12, 336, NULL,  NULL,  0.0100, 0.400, 'VALOR_CONGELADO'),
    (5, 'PERDIDA_COMUNICACION', 'Perdida de comunicacion',        'NULIFICACION',  FALSE, 1,  24, NULL,  NULL,  0.9000, 0.980, 'LECTURA_AUSENTE'),
    (6, 'SOBRECARGA',           'Sobrecarga de capacidad',        'INCREMENTO',    TRUE,  1,   6, 1.800, 3.000, 0.0150, 0.900, 'CARGA_CONTRATADA'),
    (7, 'MANTENIMIENTO',        'Mantenimiento programado',       'REDUCCION',     FALSE, 2,   8, 0.000, 0.250, 0.0200, 1.000, 'VENTANA_PROGRAMADA');

-- ============================================================
-- 5. PERFILES DE CARGA HORARIA
-- 18 tipos x 3 clases de dia x 24 horas = 1,296 filas.
-- Cada curva se normaliza para que sus 24 factores sumen 24.
-- ============================================================
WITH base AS (
    SELECT
        ts.id_tipo_servicio,
        ts.clave,
        ts.categoria,
        d.tipo_dia,
        h.hora,
        CASE
            -- Residencial: madrugada baja, picos matutino y nocturno.
            WHEN ts.categoria = 'RESIDENCIAL' THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 5  THEN 0.42
                    WHEN h.hora BETWEEN 6 AND 8  THEN 0.95
                    WHEN h.hora BETWEEN 9 AND 13 THEN 0.62
                    WHEN h.hora BETWEEN 14 AND 17 THEN 0.78
                    WHEN h.hora BETWEEN 18 AND 22 THEN 1.72
                    ELSE 0.86
                END
            -- Comercio: actividad diurna.
            WHEN ts.categoria = 'COMERCIAL' THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 6  THEN 0.18
                    WHEN h.hora BETWEEN 7 AND 8  THEN 0.70
                    WHEN h.hora BETWEEN 9 AND 18 THEN 1.65
                    WHEN h.hora BETWEEN 19 AND 21 THEN 0.75
                    ELSE 0.25
                END
            -- Alumbrado: encendido nocturno.
            WHEN ts.categoria = 'ALUMBRADO' THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 5  THEN 1.70
                    WHEN h.hora BETWEEN 6 AND 17 THEN 0.03
                    ELSE 1.75
                END
            -- Movilidad: operación continua con horas pico.
            WHEN ts.categoria = 'MOVILIDAD' THEN
                CASE
                    WHEN h.hora BETWEEN 6 AND 9  THEN 1.35
                    WHEN h.hora BETWEEN 17 AND 21 THEN 1.40
                    WHEN h.hora BETWEEN 0 AND 4  THEN 0.55
                    ELSE 0.95
                END
            -- Bombeo/agua: operación estable con refuerzo nocturno.
            WHEN ts.categoria = 'SERVICIO' THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 5 THEN 1.25
                    WHEN h.hora BETWEEN 6 AND 17 THEN 0.90
                    ELSE 1.05
                END
            -- Tipos públicos con curvas diferenciadas.
            WHEN ts.clave = 'MERCADO' THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 4 THEN 0.28
                    WHEN h.hora BETWEEN 5 AND 7 THEN 1.12
                    WHEN h.hora BETWEEN 8 AND 13 THEN 2.00
                    WHEN h.hora BETWEEN 14 AND 17 THEN 0.92
                    ELSE 0.31
                END
            WHEN ts.clave = 'ESCUELA' THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 5 THEN 0.12
                    WHEN h.hora BETWEEN 6 AND 7 THEN 0.70
                    WHEN h.hora BETWEEN 8 AND 14 THEN 2.10
                    WHEN h.hora BETWEEN 15 AND 18 THEN 0.65
                    ELSE 0.18
                END
            WHEN ts.clave IN ('CLINICA','HOSPITAL') THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 5 THEN 0.82
                    WHEN h.hora BETWEEN 6 AND 17 THEN 1.12
                    ELSE 0.98
                END
            WHEN ts.clave IN ('EDIF_GOB','BIBLIOTECA','CTRO_CULT') THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 6 THEN 0.12
                    WHEN h.hora BETWEEN 7 AND 8 THEN 0.65
                    WHEN h.hora BETWEEN 9 AND 17 THEN 1.95
                    WHEN h.hora BETWEEN 18 AND 20 THEN 0.65
                    ELSE 0.18
                END
            WHEN ts.clave IN ('CTRO_DEP','PARQUE') THEN
                CASE
                    WHEN h.hora BETWEEN 0 AND 5 THEN 0.28
                    WHEN h.hora BETWEEN 6 AND 11 THEN 0.75
                    WHEN h.hora BETWEEN 12 AND 16 THEN 1.05
                    WHEN h.hora BETWEEN 17 AND 22 THEN 1.65
                    ELSE 0.45
                END
            ELSE 1.00
        END
        *
        CASE
            -- Fin de semana por familia de servicio.
            WHEN d.tipo_dia = 'H' THEN 1.00
            WHEN d.tipo_dia = 'S' AND ts.categoria = 'RESIDENCIAL' THEN 1.08
            WHEN d.tipo_dia = 'D' AND ts.categoria = 'RESIDENCIAL' THEN 1.12
            WHEN d.tipo_dia = 'S' AND ts.clave = 'ESCUELA' THEN 0.25
            WHEN d.tipo_dia = 'D' AND ts.clave = 'ESCUELA' THEN 0.10
            WHEN d.tipo_dia IN ('S','D') AND ts.clave IN ('EDIF_GOB','BIBLIOTECA') THEN 0.30
            WHEN d.tipo_dia = 'D' AND ts.categoria = 'COMERCIAL' THEN 0.75
            ELSE 1.00
        END AS factor_bruto
    FROM tipo_servicio ts
    CROSS JOIN (VALUES ('H'::char(1)), ('S'::char(1)), ('D'::char(1))) d(tipo_dia)
    CROSS JOIN generate_series(0, 23) h(hora)
), normalizado AS (
    SELECT
        id_tipo_servicio,
        tipo_dia,
        hora,
        ROUND(
            (factor_bruto * 24.0 /
             SUM(factor_bruto) OVER (PARTITION BY id_tipo_servicio, tipo_dia))::numeric,
            4
        ) AS factor
    FROM base
)
INSERT INTO perfil_carga_horaria (
    id_tipo_servicio, tipo_dia, hora, factor
)
SELECT id_tipo_servicio, tipo_dia, hora, factor
FROM normalizado
ON CONFLICT (id_tipo_servicio, tipo_dia, hora) DO UPDATE SET
    factor = EXCLUDED.factor;

COMMIT;

-- ============================================================
-- 6. VALIDACIONES
-- ============================================================
SELECT 'zona' AS tabla, COUNT(*) AS filas FROM energia.zona
UNION ALL SELECT 'tarifa', COUNT(*) FROM energia.tarifa
UNION ALL SELECT 'tipo_servicio', COUNT(*) FROM energia.tipo_servicio
UNION ALL SELECT 'tipo_evento', COUNT(*) FROM energia.tipo_evento
UNION ALL SELECT 'perfil_carga_horaria', COUNT(*) FROM energia.perfil_carga_horaria
ORDER BY tabla;

-- Debe devolver 0 filas: cada curva debe sumar aproximadamente 24.
SELECT
    id_tipo_servicio,
    tipo_dia,
    SUM(factor) AS suma_factores
FROM energia.perfil_carga_horaria
GROUP BY id_tipo_servicio, tipo_dia
HAVING ABS(SUM(factor) - 24.0) > 0.01
ORDER BY id_tipo_servicio, tipo_dia;

-- Debe devolver 0.
SELECT COUNT(*) AS zonas_con_factor_fuera_de_rango
FROM energia.zona
WHERE factor_socioeconomico NOT BETWEEN 0.5 AND 2.0;

-- Debe devolver 0.
SELECT COUNT(*) AS zonas_sin_superficie
FROM energia.zona
WHERE superficie_km2 IS NULL OR superficie_km2 <= 0;
