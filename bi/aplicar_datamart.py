"""Aplica las vistas del datamart (bi/queries_datamart.sql) a energia_hsd.

Credenciales por variables de entorno (con fallback local de demo):
  PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

Uso:
  python bi/aplicar_datamart.py
"""
import os
import sys

import psycopg

BASE = os.path.dirname(os.path.abspath(__file__))
SQL = os.path.join(BASE, "queries_datamart.sql")

con = psycopg.connect(
    f"host={os.getenv('PGHOST', 'localhost')} "
    f"port={os.getenv('PGPORT', '5433')} "
    f"dbname={os.getenv('PGDATABASE', 'energia_hsd')} "
    f"user={os.getenv('PGUSER', 'equipo_hsd')} "
    f"password={os.getenv('PGPASSWORD', 'hsd_test_2026')}",
    connect_timeout=10,
)
con.autocommit = True
cur = con.cursor()

with open(SQL, encoding="utf-8") as f:
    sentencias = "".join(
        line for line in f if not line.strip().startswith("--")
    )

ok = 0
for sentencia in sentencias.split(";"):
    if not sentencia.strip():
        continue
    nombre = sentencia.strip().split()[0:4]
    try:
        cur.execute(sentencia)
        ok += 1
        print("[OK]", " ".join(nombre))
    except Exception as exc:
        print("[ERROR]", " ".join(nombre), "->", exc)

# Verificacion
for v in [
    "dm_consumo_diario",
    "dm_consumo_hora",
    "dm_consumo_por_tipo",
    "dm_consumo_por_zona",
    "dm_eventos",
    "dm_alertas",
    "dm_saldo_servicio",
]:
    cur.execute(f"SELECT count(*) FROM energia.{v}")
    print(f"  {v}: {cur.fetchone()[0]} filas")

print(f"\nDatamart: {ok}/7 vistas aplicadas")
con.close()
sys.exit(0 if ok == 7 else 1)