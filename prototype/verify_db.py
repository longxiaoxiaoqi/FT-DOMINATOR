import sqlite3
from pathlib import Path

db = sqlite3.connect(Path(__file__).parent / "data" / "test_assets.db")
print("tables=", [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")])
print("assets=", db.execute("SELECT COUNT(*) FROM assets").fetchone()[0])
print("shipments=", db.execute("SELECT COUNT(*) FROM shipments").fetchone()[0])
print("releases=", db.execute("SELECT COUNT(*) FROM releases").fetchone()[0])
print("indexes=", [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%' ORDER BY name")])
print("quick_check=", db.execute("PRAGMA quick_check").fetchone()[0])
