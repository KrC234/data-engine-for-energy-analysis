-- ============================================================
-- HyperDataSynthetic BI - Datamart sobre energia_hsd
-- 7 vistas agregadas de la corrida de 10.8M lecturas
-- ============================================================

CREATE OR REPLACE VIEW energia.dm_consumo_diario AS
SELECT CAST(l.ts AS date) AS fecha,
       to_char(CAST(l.ts AS date), 'TMDay') AS dia_semana,
       count(*) AS lecturas,
       sum(l.consumo_real_kwh) AS consumo_real_kwh,
       sum(l.consumo_kwh) AS consumo_facturado_kwh
FROM energia.lectura l
GROUP BY 1, 2
ORDER BY 1;

CREATE OR REPLACE VIEW energia.dm_consumo_hora AS
SELECT CAST(l.ts AS date) AS fecha,
       EXTRACT(hour FROM l.ts)::int AS hora,
       round(avg(l.consumo_real_kwh), 4) AS consumo_promedio_kwh,
       sum(l.consumo_real_kwh) AS consumo_total_kwh
FROM energia.lectura l
GROUP BY 1, 2
ORDER BY 1, 2;

CREATE OR REPLACE VIEW energia.dm_consumo_por_tipo AS
SELECT t.clave AS tipo_servicio,
       CAST(l.ts AS date) AS fecha,
       count(*) AS lecturas,
       sum(l.consumo_real_kwh) AS consumo_real_kwh
FROM energia.lectura l
JOIN energia.medidor m ON m.id_medidor = l.id_medidor
JOIN energia.servicio s ON s.id_servicio = m.id_servicio
JOIN energia.tipo_servicio t ON t.id_tipo_servicio = s.id_tipo_servicio
GROUP BY 1, 2
ORDER BY 2, 1;

CREATE OR REPLACE VIEW energia.dm_consumo_por_zona AS
SELECT z.nombre AS zona, z.tipo_urbano,
       s.id_tipo_servicio,
       sum(l.consumo_real_kwh) AS consumo_real_kwh,
       count(*) AS lecturas
FROM energia.lectura l
JOIN energia.medidor m ON m.id_medidor = l.id_medidor
JOIN energia.servicio s ON s.id_servicio = m.id_servicio
JOIN energia.zona z ON z.id_zona = s.id_zona
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW energia.dm_eventos AS
SELECT te.clave AS tipo_evento, te.efecto,
       count(*) AS n_eventos,
       sum(e.kwh_desviados) AS kwh_desviados
FROM energia.evento e
JOIN energia.tipo_evento te ON te.id_tipo_evento = e.id_tipo_evento
GROUP BY 1, 2
ORDER BY 3 DESC;

CREATE OR REPLACE VIEW energia.dm_alertas AS
SELECT te.clave AS tipo_evento,
       a.prioridad,
       count(*) AS n_alertas,
       count(a.ts_cierre) AS cerradas
FROM energia.alerta a
JOIN energia.tipo_evento te ON te.id_tipo_evento = a.id_tipo_evento
GROUP BY 1, 2
ORDER BY 3 DESC;

CREATE OR REPLACE VIEW energia.dm_saldo_servicio AS
SELECT ts.clave AS tipo_servicio,
       count(*) AS lecturas_nulas,
       sum(l.consumo_real_kwh) AS consumo_real_kwh
FROM energia.lectura l
JOIN energia.medidor m ON m.id_medidor = l.id_medidor
JOIN energia.servicio s ON s.id_servicio = m.id_servicio
JOIN energia.tipo_servicio ts ON ts.id_tipo_servicio = s.id_tipo_servicio
WHERE l.consumo_kwh IS NULL
GROUP BY 1;