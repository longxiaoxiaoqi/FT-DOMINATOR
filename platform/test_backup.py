import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from backup import create, restore, verify


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        with closing(sqlite3.connect(self.source / 'ft.sqlite3')) as db:
            db.execute('CREATE TABLE sample (name TEXT)')
            db.execute('INSERT INTO sample VALUES (?)', ('隔离测试',))
            db.commit()
        (self.source / 'uploads').mkdir()
        (self.source / 'uploads' / '图纸.bin').write_bytes(b'attachment\x00data')
        (self.source / 'secret-key.txt').write_text('isolated-test-secret')
        self.backup = create(self.source)

    def test_round_trip_and_existing_destination(self):
        verify(self.backup)
        target = restore(self.backup, self.base / 'restored')
        with closing(sqlite3.connect(target / 'ft.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT name FROM sample').fetchone()[0], '隔离测试')
        self.assertEqual((target / 'uploads' / '图纸.bin').read_bytes(), b'attachment\x00data')
        self.assertEqual((target / 'secret-key.txt').read_text(), 'isolated-test-secret')
        with self.assertRaises(ValueError):
            restore(self.backup, target)
        verify(self.backup)

    def test_corrupt_attachment_refuses_restore(self):
        (self.backup / 'uploads' / '图纸.bin').write_bytes(b'corrupted')
        target = self.base / 'rejected'
        with self.assertRaises(ValueError):
            restore(self.backup, target)
        self.assertFalse(target.exists())

    def test_missing_file(self):
        (self.backup / 'secret-key.txt').unlink()
        with self.assertRaises(ValueError):
            verify(self.backup)

    def test_extra_file(self):
        (self.backup / 'unexpected.txt').write_text('extra')
        with self.assertRaises(ValueError):
            verify(self.backup)

    def test_invalid_manifest(self):
        (self.backup / 'manifest.json').write_text(json.dumps({'format': 99, 'files': {}}))
        with self.assertRaises(ValueError):
            verify(self.backup)

    def test_missing_database_does_not_create_backup(self):
        empty = self.base / 'empty'
        empty.mkdir()
        with self.assertRaises(ValueError):
            create(empty)
        self.assertFalse((empty / 'backups').exists())

    def test_repeated_backups_have_distinct_names(self):
        second = create(self.source)
        self.assertNotEqual(self.backup, second)
        verify(second)


if __name__ == '__main__':
    unittest.main()
