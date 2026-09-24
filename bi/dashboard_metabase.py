"""Crea el dashboard BI en Metabase para la corrida de 10.8M.

Requisitos (ver README_BI.md):
  1. cliente de instalaciones: docker network create hsd_net
     docker network connect hsd_net postgres_hsd
     docker run -d --name metabase_hsd -p 3000:3000 --restart unless-stopped \
       -v metabase_data:/metabase.db -e MB_DB_FILE=/metabase.db/metabase.db \
       -e MB_JETTY_HOST=0.0.0.0 --network hsd_net metabase/metabase
  2. pip install psycopg (para aplicar_datamart.py) y python apply bi/aplicar_datamart.py

Variables de entorno (fallback = entorno local de demostracion):
  MB_URL, MB_ADMIN_EMAIL, MB_ADMIN_PASSWORD
  PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

Nota API Metabase v0.63: POST/DELETE /dashboard/:id/cards NO existen.
Las tarjetas se crean/actualizan con PUT /api/dashboard/{id} usando IDs
negativos (crear) y claves snake_case: size_x, size_y, col, row.
"""
import json
import os
import urllib.request

MB_URL = os.getenv("MB_URL", "http://localhost:3000")
MB_ADMIN = os.getenv("MB_ADMIN_EMAIL", "equipo.hsd@local.test")
MB_PWD = os.getenv("MB_ADMIN_PASSWORD", "hsd_admin_2026")

DB_HOST = os.getenv("PGHOST", "postgres_hsd")
DB_PORT = os.getenv("PGPORT", "5432")
DB_NAME = os.getenv("PGDATABASE", "energia_hsd")
DB_USER = os.getenv("PGUSER", "equipo_hsd")
DB_PWD = os.getenv("PGPASSWORD", "hsd_test_2026")


def api(method, path, body=None, session=None):
    url = MB_URL + "/api" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if session:
        req.add_header("X-Metabase-Session", session)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, path, e.read().decode()[:300])
        raise


# 1) Login (o setup inicial si es la primera vez)
try:
    session = api("POST", "/session", {"username": MB_ADMIN, "password": MB_PWD})["id"]
except Exception:
    props = api("GET", "/session/properties")
    token = props.get("setup-token")
    if not token:
        raise SystemExit("Metabase ya tiene admin; revise MB_ADMIN_EMAIL/PASSWORD")
    setup = api(
        "POST",
        "/setup",
        {
            "token": token,
            "prefs": {"site_name": "HyperDataSynthetic", "allow_tracking": False},
            "user": {"first_name": "Equipo", "last_name": "HSD", "email": MB_ADMIN, "password": MB_PWD},
            "database": {"engine": "postgres", "name": DB_NAME, "details": {"host": DB_HOST, "port": int(DB_PORT), "dbname": DB_NAME, "user": DB_USER, "password": DB_PWD, "ssl": False}, "is_full_sync": True},
        },
    )
    session = setup["id"]
print("Login OK")

# 2) Conexion a la base (si no existe)
db_id = None
for d in api("GET", "/database", session=session)["data"]:
    if d["name"] == DB_NAME:
        db_id = d["id"]
        break
if db_id is None:
    db_id = api(
        "POST",
        "/database",
        {"engine": "postgres", "name": DB_NAME, "details": {"host": DB_HOST, "port": int(DB_PORT), "dbname": DB_NAME, "user": DB_USER, "password": DB_PWD, "ssl": False}, "is_full_sync": True},
        session,
    )["id"]
print("Database id:", db_id)

# 3) Tarjetas SQL nativas sobre el datamart
CARDS = [
    ("Consumo diario (kWh)", "line",
     "SELECT fecha, round(consumo_real_kwh,1) AS consumo_real_kwh, round(consumo_facturado_kwh,1) AS consumo_facturado_kwh FROM energia.dm_consumo_diario ORDER BY fecha"),
    ("Curva de carga promedio por hora", "line",
     "SELECT hora, round(avg(consumo_promedio_kwh),3) AS promedio_kwh FROM energia.dm_consumo_hora GROUP BY hora ORDER BY hora"),
    ("Consumo total por tipo de servicio", "bar",
     "SELECT tipo_servicio, round(sum(consumo_real_kwh),1) AS kwh FROM energia.dm_consumo_por_tipo GROUP BY 1 ORDER BY 2 DESC"),
    ("Consumo por zona (top 15)", "bar",
     "SELECT zona, round(sum(consumo_real_kwh),1) AS kwh FROM energia.dm_consumo_por_zona GROUP BY 1 ORDER BY 2 DESC LIMIT 15"),
    ("Eventos por tipo", "bar",
     "SELECT tipo_evento, n_eventos, round(kwh_desviados,1) AS kwh_desviados FROM energia.dm_eventos ORDER BY n_eventos DESC"),
    ("Alertas por prioridad", "bar",
     "SELECT tipo_evento, prioridad, sum(n_alertas) AS n_alertas FROM energia.dm_alertas GROUP BY 1, 2 ORDER BY 2"),
    ("Perdida de comunicacion (kWh sin facturar)", "bar",
     "SELECT tipo_servicio, lecturas_nulas, round(consumo_real_kwh,1) AS kwh FROM energia.dm_saldo_servicio ORDER BY lecturas_nulas DESC"),
]

card_ids = []
for name, display, query in CARDS:
    card = api(
        "POST",
        "/card",
        {
            "name": name,
            "display": display,
            "dataset_query": {"database": db_id, "type": "native", "native": {"query": query, "template-tags": {}}},
            "visualization_settings": {},
        },
        session,
    )
    card_ids.append(card["id"])
    print("Card:", name, "->", card["id"])

# 4) Dashboard
dash = api("POST", "/dashboard", {"name": "HyperDataSynthetic - Monitoreo de Consumo Energetico"}, session)
dash_id = dash["id"]

layout = [
    {"col": 0, "row": 0, "size_x": 9, "size_y": 7},
    {"col": 9, "row": 0, "size_x": 7, "size_y": 7},
    {"col": 0, "row": 7, "size_x": 5, "size_y": 7},
    {"col": 5, "row": 7, "size_x": 5, "size_y": 7},
    {"col": 10, "row": 7, "size_x": 6, "size_y": 7},
    {"col": 0, "row": 14, "size_x": 6, "size_y": 6},
    {"col": 6, "row": 14, "size_x": 6, "size_y": 6},
]
dashcards = [
    {"id": -(i + 1), "card_id": cid, "visualization_settings": {}, "series": [], "parameter_mappings": [], **pos}
    for i, (cid, pos) in enumerate(zip(card_ids, layout))
]
r = api(
    "PUT",
    f"/dashboard/{dash_id}",
    {"name": "HyperDataSynthetic - Monitoreo de Consumo Energetico", "description": None, "width": "full", "tabs": dash.get("tabs", []), "dashcards": dashcards},
    session,
)
print("Tarjetas en dashboard:", len(r.get("dashcards", [])))

print("\n=== LISTO ===")
print("URL:", f"{MB_URL}/dashboard/{dash_id}")
print("Login:", MB_ADMIN, "/", MB_PWD)