import sqlite3
from pathlib import Path

root = Path(__file__).parent
db = sqlite3.connect(root / "data" / "test_assets.db")
rows = db.execute("SELECT stored_name FROM files WHERE original_name='upload-test.txt'").fetchall()
db.execute("DELETE FROM files WHERE original_name='upload-test.txt'")
db.execute("UPDATE assets SET file_name='A100_LB图纸_RevB.pdf' WHERE id='LB-A100-01'")
db.commit()
for (stored_name,) in rows:
    (root / "uploads" / stored_name).unlink(missing_ok=True)
(root / "upload-test.txt").unlink(missing_ok=True)
(root / "download-verify.txt").unlink(missing_ok=True)
print("test_uploads_removed=", len(rows))
