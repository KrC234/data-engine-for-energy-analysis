# BI HyperDataSynthetic - Datamart + Dashboard Metabase

Dashboard de monitoreo construido sobre la corrida completa de **10.8M lecturas**
(5,000 servicios x 90 dias, ene-mar 2026). Herramientas 100% open source.

## Contenido
- `queries_datamart.sql`: 7 vistas agregadas (`energia.dm_*`) sobre PostgreSQL.
- `aplicar_datamart.py`: aplica las vistas (usa variables de entorno
  `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`, fallback al entorno local).
- `dashboard_metabase.py`: crea la conexion, 7 preguntas SQL nativas y el
  dashboard en Metabase (fallback: `MB_URL/MB_ADMIN_EMAIL/MB_ADMIN_PASSWORD`).
- `../resultados_corrida_10M.csv`: resultados consolidados de la corrida.

## Pasos para reproducir

```bash
# 1) Datamart en PostgreSQL
python bi/aplicar_datamart.py

# 2) Levantar Metabase conectado a postgres (misma red de Docker)
docker network create hsd_net
docker network connect hsd_net postgres_hsd
docker run -d --name metabase_hsd -p 3000:3000 --restart unless-stopped \
  -v metabase_data:/metabase.db -e MB_DB_FILE=/metabase.db/metabase.db \
  -e MB_JETTY_HOST=0.0.0.0 --network hsd_net metabase/metabase

# 3) Esperar a que arranque (1-2 min) y configurar
python bi/dashboard_metabase.py
```

Acceso: `http://localhost:3000/dashboard/2`
(admin local de demo: `equipo.hsd@local.test` / `hsd_admin_2026`; cambiarla en
produccion con las variables de entorno).

## Resultados clave de la corrida
- 10,800,000 lecturas en 82 segundos (validacion PASO, minimo 10M).
- Total registros: 10,839,782.
- Consumo real total: 38,593,166 kWh en 90 dias.
- 7,296 eventos | 7,136 alertas (339 falsas prioridad 4) | 15,000 periodos.

## Tarjetas del dashboard
1. Consumo diario (kWh) - linea
2. Curva de carga promedio por hora - linea
3. Consumo total por tipo de servicio - barras
4. Consumo por zona (top 15) - barras
5. Eventos por tipo - barras
6. Alertas por prioridad - barras
7. Perdida de comunicacion (kWh sin facturar) - barras

## Nota de API (Metabase v0.63)
`POST/DELETE /api/dashboard/:id/cards` no existen desde v0.47. Las tarjetas se
crean con `PUT /api/dashboard/{id}` usando IDs negativos y claves `snake_case`
(`size_x`, `size_y`, `col`, `row`). Documentado para no repetir el tropiezo.