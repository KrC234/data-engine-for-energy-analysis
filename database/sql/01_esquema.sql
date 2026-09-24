-- ============================================================
--  01_esquema.sql
--  Sistema de Monitoreo Energetico - Valle de Nexpahuacan
--  Programa piloto de medicion inteligente
--
--  Ejecutar conectado a la base "energia_hsd":
--
--      psql -U equipo_hsd -d energia_hsd -h localhost -f 01_esquema.sql
--
--  Crea el esquema, las 13 tablas en orden de dependencias,
--  las particiones mensuales de "lectura" y los indices.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS energia;
SET search_path TO energia;

-- ------------------------------------------------------------
-- corrida_generacion (se crea primero: documenta el proceso completo)
-- ------------------------------------------------------------
CREATE TABLE corrida_generacion (
    id_corrida          SMALLINT      NOT NULL,
    nombre              VARCHAR(40)   NOT NULL,
    semilla             BIGINT        NOT NULL,
    version_reglas      VARCHAR(12)   NOT NULL,
    hash_parametros     CHAR(64)      NOT NULL,
    ts_inicio_ejecucion TIMESTAMP     NOT NULL,
    ts_fin_ejecucion    TIMESTAMP,
    fecha_desde         DATE          NOT NULL,
    fecha_hasta         DATE          NOT NULL,
    intervalo_min       SMALLINT      NOT NULL,
    total_lecturas      BIGINT,
    notas               VARCHAR(300),

    CONSTRAINT pk_corrida        PRIMARY KEY (id_corrida),
    CONSTRAINT uq_corrida_params UNIQUE (semilla, version_reglas, hash_parametros),
    CONSTRAINT ck_corrida_fechas CHECK (fecha_hasta >= fecha_desde),
    CONSTRAINT ck_corrida_interv CHECK (intervalo_min IN (5, 15, 30, 60))
);

-- ------------------------------------------------------------
-- zona
-- ------------------------------------------------------------
CREATE TABLE zona (
    id_zona               SMALLINT      NOT NULL,
    nombre                VARCHAR(60)   NOT NULL,
    tipo_urbano           VARCHAR(20)   NOT NULL,
    superficie_km2        NUMERIC(6,3)  NOT NULL,
    factor_socioeconomico NUMERIC(4,3)  NOT NULL,

    CONSTRAINT pk_zona        PRIMARY KEY (id_zona),
    CONSTRAINT uq_zona_nombre UNIQUE (nombre),
    CONSTRAINT ck_zona_tipo   CHECK (tipo_urbano IN ('CENTRO','RESIDENCIAL_ALTA',
                                'RESIDENCIAL_MEDIA','POPULAR','MIXTA','PERIFERIA')),
    CONSTRAINT ck_zona_sup    CHECK (superficie_km2 > 0),
    CONSTRAINT ck_zona_socio  CHECK (factor_socioeconomico BETWEEN 0.5 AND 2.0)
);

-- ------------------------------------------------------------
-- tarifa
-- ------------------------------------------------------------
CREATE TABLE tarifa (
    id_tarifa          SMALLINT     NOT NULL,
    codigo             VARCHAR(6)   NOT NULL,
    nombre             VARCHAR(60)  NOT NULL,
    categoria          VARCHAR(18)  NOT NULL,
    limite_dac_kwh_mes INTEGER,

    CONSTRAINT pk_tarifa      PRIMARY KEY (id_tarifa),
    CONSTRAINT uq_tarifa_cod  UNIQUE (codigo),
    CONSTRAINT ck_tarifa_cat  CHECK (categoria IN ('DOMESTICA','COMERCIAL',
                                'SERVICIO_PUBLICO','ALUMBRADO')),
    CONSTRAINT ck_tarifa_dac  CHECK (limite_dac_kwh_mes IS NULL OR limite_dac_kwh_mes > 0)
);

-- ------------------------------------------------------------
-- tipo_servicio
-- ------------------------------------------------------------
CREATE TABLE tipo_servicio (
    id_tipo_servicio   SMALLINT      NOT NULL,
    clave              VARCHAR(14)   NOT NULL,
    nombre             VARCHAR(60)   NOT NULL,
    categoria          VARCHAR(12)   NOT NULL,
    consumo_base_kwh_h NUMERIC(8,3)  NOT NULL,
    factor_dispersion  NUMERIC(4,3)  NOT NULL,
    sensibilidad_temp  NUMERIC(4,3)  NOT NULL,

    CONSTRAINT pk_tiposrv       PRIMARY KEY (id_tipo_servicio),
    CONSTRAINT uq_tiposrv_clave UNIQUE (clave),
    CONSTRAINT ck_tiposrv_cat   CHECK (categoria IN ('RESIDENCIAL','COMERCIAL',
                                  'PUBLICO','SERVICIO','ALUMBRADO','MOVILIDAD')),
    CONSTRAINT ck_tiposrv_cons  CHECK (consumo_base_kwh_h > 0),
    CONSTRAINT ck_tiposrv_disp  CHECK (factor_dispersion BETWEEN 0 AND 2),
    CONSTRAINT ck_tiposrv_temp  CHECK (sensibilidad_temp BETWEEN 0 AND 1)
);

-- ------------------------------------------------------------
-- tipo_evento
-- ------------------------------------------------------------
CREATE TABLE tipo_evento (
    id_tipo_evento       SMALLINT      NOT NULL,
    clave                VARCHAR(20)   NOT NULL,
    nombre               VARCHAR(60)   NOT NULL,
    efecto               VARCHAR(14)   NOT NULL,
    afecta_acumulado     BOOLEAN       NOT NULL,
    duracion_min_h       SMALLINT      NOT NULL,
    duracion_max_h       SMALLINT      NOT NULL,
    intensidad_min       NUMERIC(5,3),
    intensidad_max       NUMERIC(5,3),
    tasa_por_medidor_mes NUMERIC(6,4)  NOT NULL,
    prob_deteccion       NUMERIC(4,3)  NOT NULL,
    regla_deteccion      VARCHAR(30)   NOT NULL,

    CONSTRAINT pk_tipoev        PRIMARY KEY (id_tipo_evento),
    CONSTRAINT uq_tipoev_clave  UNIQUE (clave),
    CONSTRAINT ck_tipoev_efecto CHECK (efecto IN ('INCREMENTO','REDUCCION',
                                  'CONGELAMIENTO','NULIFICACION')),
    CONSTRAINT ck_tipoev_dur    CHECK (duracion_max_h >= duracion_min_h
                                       AND duracion_min_h > 0),
    CONSTRAINT ck_tipoev_int    CHECK (intensidad_max IS NULL
                                       OR intensidad_max >= intensidad_min),
    CONSTRAINT ck_tipoev_tasa   CHECK (tasa_por_medidor_mes >= 0),
    CONSTRAINT ck_tipoev_det    CHECK (prob_deteccion BETWEEN 0 AND 1)
);

-- ------------------------------------------------------------
-- perfil_carga_horaria (depende de tipo_servicio)
-- ------------------------------------------------------------
CREATE TABLE perfil_carga_horaria (
    id_tipo_servicio SMALLINT      NOT NULL,
    tipo_dia         CHAR(1)       NOT NULL,
    hora             SMALLINT      NOT NULL,
    factor           NUMERIC(5,4)  NOT NULL,

    CONSTRAINT pk_perfil        PRIMARY KEY (id_tipo_servicio, tipo_dia, hora),
    CONSTRAINT fk_perfil_tipo   FOREIGN KEY (id_tipo_servicio)
                                REFERENCES tipo_servicio (id_tipo_servicio)
                                ON DELETE CASCADE,
    CONSTRAINT ck_perfil_dia    CHECK (tipo_dia IN ('H','S','D')),
    CONSTRAINT ck_perfil_hora   CHECK (hora BETWEEN 0 AND 23),
    CONSTRAINT ck_perfil_factor CHECK (factor >= 0 AND factor <= 6)
);

-- ------------------------------------------------------------
-- calendario
-- ------------------------------------------------------------
CREATE TABLE calendario (
    fecha             DATE          NOT NULL,
    tipo_dia          CHAR(1)       NOT NULL,
    es_festivo        BOOLEAN       NOT NULL,
    es_vacacional     BOOLEAN       NOT NULL,
    temp_min_c        NUMERIC(4,1)  NOT NULL,
    temp_max_c        NUMERIC(4,1)  NOT NULL,
    factor_estacional NUMERIC(5,4)  NOT NULL,

    CONSTRAINT pk_calendario     PRIMARY KEY (fecha),
    CONSTRAINT ck_cal_tipo       CHECK (tipo_dia IN ('H','S','D')),
    CONSTRAINT ck_cal_trango     CHECK (temp_max_c > temp_min_c),
    CONSTRAINT ck_cal_estacional CHECK (factor_estacional BETWEEN 0.5 AND 2.0)
);

-- ------------------------------------------------------------
-- servicio (depende de zona, tipo_servicio, tarifa)
-- ------------------------------------------------------------
CREATE TABLE servicio (
    id_servicio         INTEGER       NOT NULL,
    rpu                 CHAR(12)      NOT NULL,
    id_zona             SMALLINT      NOT NULL,
    id_tipo_servicio    SMALLINT      NOT NULL,
    id_tarifa           SMALLINT      NOT NULL,
    nombre              VARCHAR(120)  NOT NULL,
    latitud             NUMERIC(9,6)  NOT NULL,
    longitud            NUMERIC(9,6)  NOT NULL,
    ocupacion_estimada  SMALLINT,
    carga_contratada_kw NUMERIC(8,2)  NOT NULL,
    tiene_solar         BOOLEAN       NOT NULL DEFAULT FALSE,

    CONSTRAINT pk_servicio      PRIMARY KEY (id_servicio),
    CONSTRAINT uq_servicio_rpu  UNIQUE (rpu),
    CONSTRAINT uq_servicio_nom  UNIQUE (id_zona, nombre),
    CONSTRAINT fk_servicio_zona FOREIGN KEY (id_zona)
                                REFERENCES zona (id_zona) ON DELETE RESTRICT,
    CONSTRAINT fk_servicio_tipo FOREIGN KEY (id_tipo_servicio)
                                REFERENCES tipo_servicio (id_tipo_servicio)
                                ON DELETE RESTRICT,
    CONSTRAINT fk_servicio_tar  FOREIGN KEY (id_tarifa)
                                REFERENCES tarifa (id_tarifa) ON DELETE RESTRICT,
    CONSTRAINT ck_servicio_rpu  CHECK (rpu ~ '^[0-9]{12}$'),
    CONSTRAINT ck_servicio_ocup CHECK (ocupacion_estimada IS NULL
                                       OR ocupacion_estimada BETWEEN 1 AND 5000),
    CONSTRAINT ck_servicio_lat  CHECK (latitud  BETWEEN -90  AND 90),
    CONSTRAINT ck_servicio_lon  CHECK (longitud BETWEEN -180 AND 180),
    CONSTRAINT ck_servicio_kw   CHECK (carga_contratada_kw > 0)
);

CREATE INDEX ix_servicio_zona ON servicio (id_zona);
CREATE INDEX ix_servicio_tipo ON servicio (id_tipo_servicio);

-- ------------------------------------------------------------
-- medidor (depende de servicio)
-- ------------------------------------------------------------
CREATE TABLE medidor (
    id_medidor        INTEGER      NOT NULL,
    id_servicio       INTEGER      NOT NULL,
    numero_serie      VARCHAR(24)  NOT NULL,
    marca             VARCHAR(24)  NOT NULL,
    multiplicador     SMALLINT     NOT NULL DEFAULT 1,
    fecha_instalacion DATE         NOT NULL,
    fecha_retiro      DATE,
    calidad_enlace    SMALLINT     NOT NULL,

    CONSTRAINT pk_medidor        PRIMARY KEY (id_medidor),
    CONSTRAINT uq_medidor_serie  UNIQUE (numero_serie),
    CONSTRAINT fk_medidor_srv    FOREIGN KEY (id_servicio)
                                 REFERENCES servicio (id_servicio) ON DELETE RESTRICT,
    CONSTRAINT ck_medidor_vig    CHECK (fecha_retiro IS NULL
                                        OR fecha_retiro > fecha_instalacion),
    CONSTRAINT ck_medidor_enlace CHECK (calidad_enlace BETWEEN 50 AND 100),
    CONSTRAINT ck_medidor_mult   CHECK (multiplicador IN (1, 20, 40, 80))
);

CREATE INDEX ix_medidor_servicio ON medidor (id_servicio);
CREATE INDEX ix_medidor_marca    ON medidor (marca);

-- ------------------------------------------------------------
-- evento (depende de medidor, tipo_evento)
-- se crea antes que "lectura" porque esta ultima la referencia
-- ------------------------------------------------------------
CREATE TABLE evento (
    id_evento      BIGINT         NOT NULL,
    id_medidor     INTEGER        NOT NULL,
    id_tipo_evento SMALLINT       NOT NULL,
    ts_inicio      TIMESTAMP      NOT NULL,
    ts_fin         TIMESTAMP      NOT NULL,
    intensidad     NUMERIC(5,3),
    kwh_desviados  NUMERIC(12,4)  NOT NULL DEFAULT 0,

    CONSTRAINT pk_evento       PRIMARY KEY (id_evento),
    CONSTRAINT fk_evento_med   FOREIGN KEY (id_medidor)
                               REFERENCES medidor (id_medidor),
    CONSTRAINT fk_evento_tipo  FOREIGN KEY (id_tipo_evento)
                               REFERENCES tipo_evento (id_tipo_evento),
    CONSTRAINT ck_evento_rango CHECK (ts_fin > ts_inicio)
);

CREATE INDEX ix_evento_medidor_ts ON evento (id_medidor, ts_inicio);
CREATE INDEX ix_evento_tipo       ON evento (id_tipo_evento);

-- ------------------------------------------------------------
-- lectura (depende de medidor, evento) - particionada por mes
-- ------------------------------------------------------------
CREATE TABLE lectura (
    id_medidor       INTEGER       NOT NULL,
    ts               TIMESTAMP     NOT NULL,
    consumo_kwh      NUMERIC(9,4),
    consumo_real_kwh NUMERIC(9,4)  NOT NULL,
    id_evento        BIGINT,

    CONSTRAINT pk_lectura       PRIMARY KEY (id_medidor, ts),

    CONSTRAINT ck_lect_consumo  CHECK (consumo_kwh IS NULL OR consumo_kwh >= 0),
    CONSTRAINT ck_lect_real     CHECK (consumo_real_kwh >= 0)
) PARTITION BY RANGE (ts);

-- Una particion por cada uno de los tres meses del periodo observado
CREATE TABLE lectura_2026_01 PARTITION OF lectura
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE lectura_2026_02 PARTITION OF lectura
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
CREATE TABLE lectura_2026_03 PARTITION OF lectura
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');



-- ------------------------------------------------------------
-- alerta (depende de evento, medidor, tipo_evento)
-- ------------------------------------------------------------
CREATE TABLE alerta (
    id_alerta      BIGINT       NOT NULL,
    id_evento      BIGINT,                     -- NULL = falsa alarma
    id_medidor     INTEGER      NOT NULL,
    id_tipo_evento SMALLINT     NOT NULL,
    ts_generacion  TIMESTAMP    NOT NULL,
    prioridad      SMALLINT     NOT NULL,
    ts_cierre      TIMESTAMP,
    resultado      VARCHAR(15),

    CONSTRAINT pk_alerta       PRIMARY KEY (id_alerta),
    CONSTRAINT fk_alerta_ev    FOREIGN KEY (id_evento)
                               REFERENCES evento (id_evento) ON DELETE SET NULL,
    CONSTRAINT fk_alerta_med   FOREIGN KEY (id_medidor)
                               REFERENCES medidor (id_medidor),
    CONSTRAINT fk_alerta_tipo  FOREIGN KEY (id_tipo_evento)
                               REFERENCES tipo_evento (id_tipo_evento),
    CONSTRAINT ck_alerta_prio  CHECK (prioridad BETWEEN 1 AND 4),
    CONSTRAINT ck_alerta_res   CHECK (resultado IS NULL OR resultado IN
                                 ('CONFIRMADA','FALSO_POSITIVO','NO_CONCLUYENTE')),
    CONSTRAINT ck_alerta_dict  CHECK ((resultado IS NULL) = (ts_cierre IS NULL)),
    CONSTRAINT ck_alerta_orden CHECK (ts_cierre IS NULL OR ts_cierre >= ts_generacion)
);

CREATE INDEX ix_alerta_evento  ON alerta (id_evento);
CREATE INDEX ix_alerta_medidor ON alerta (id_medidor);

-- ------------------------------------------------------------
-- periodo_facturacion (depende de servicio, tarifa)
-- ------------------------------------------------------------
CREATE TABLE periodo_facturacion (
    id_periodo           INTEGER        NOT NULL,
    id_servicio          INTEGER        NOT NULL,
    folio                VARCHAR(20)    NOT NULL,
    fecha_inicio         DATE           NOT NULL,
    fecha_fin            DATE           NOT NULL,
    id_tarifa_aplicada   SMALLINT       NOT NULL,
    registro_inicial_kwh NUMERIC(12,3)  NOT NULL,
    registro_final_kwh   NUMERIC(12,3)  NOT NULL,
    consumo_real_kwh     NUMERIC(12,3)  NOT NULL,
    clasificacion_dac    BOOLEAN        NOT NULL DEFAULT FALSE,

    CONSTRAINT pk_periodo        PRIMARY KEY (id_periodo),
    CONSTRAINT uq_periodo_folio  UNIQUE (folio),
    CONSTRAINT uq_periodo_srv    UNIQUE (id_servicio, fecha_inicio),
    CONSTRAINT fk_periodo_srv    FOREIGN KEY (id_servicio)
                                 REFERENCES servicio (id_servicio) ON DELETE RESTRICT,
    CONSTRAINT fk_periodo_tar    FOREIGN KEY (id_tarifa_aplicada)
                                 REFERENCES tarifa (id_tarifa),
    CONSTRAINT ck_periodo_fechas CHECK (fecha_fin > fecha_inicio),
    CONSTRAINT ck_periodo_reg    CHECK (registro_final_kwh >= registro_inicial_kwh),
    CONSTRAINT ck_periodo_real   CHECK (consumo_real_kwh >= 0)
);

CREATE INDEX ix_periodo_servicio ON periodo_facturacion (id_servicio, fecha_inicio);

-- ------------------------------------------------------------
-- Confirmacion final: lista las 13 tablas recien creadas
-- ------------------------------------------------------------
\dt energia.*



