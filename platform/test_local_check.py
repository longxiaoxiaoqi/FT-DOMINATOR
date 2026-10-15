from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from local_check import check_data, BASE


class LocalCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with closing(sqlite3.connect(self.root / 'ft.sqlite3')) as db:
            for table in ('core_attachment', 'core_taskattachment'):
                db.execute('CREATE TABLE ' + table + ' (stored_name TEXT)')
            db.execute('CREATE TABLE auth_user (id INTEGER)')
            db.execute('CREATE TABLE django_migrations (app TEXT, name TEXT)')
            for path in (BASE / 'core/migrations').glob('[0-9]*.py'):
                db.execute('INSERT INTO django_migrations VALUES (?, ?)', ('core', path.stem))
            db.commit()

    def test_complete_database_checked_without_modification(self):
        before = (self.root / 'ft.sqlite3').read_bytes()
        result = check_data(self.root)
        self.assertTrue(result['database_integrity'])
        self.assertEqual(result['missing_attachments'], 0)
        self.assertEqual(result['pending_core_migrations'], 0)
        self.assertEqual((self.root / 'ft.sqlite3').read_bytes(), before)

    def test_missing_and_unsafe_attachment_counts(self):
        with closing(sqlite3.connect(self.root / 'ft.sqlite3')) as db:
            db.execute('INSERT INTO core_attachment VALUES (?)', ('missing.pdf',))
            db.execute('INSERT INTO core_taskattachment VALUES (?)', ('../outside.pdf',))
            db.commit()
        result = check_data(self.root)
        self.assertEqual(result['missing_attachments'], 1)
        self.assertEqual(result['unsafe_attachment_paths'], 1)

    def test_unapplied_migration_detected(self):
        with closing(sqlite3.connect(self.root / 'ft.sqlite3')) as db:
            db.execute('DELETE FROM django_migrations')
            db.commit()
        self.assertGreater(check_data(self.root)['pending_core_migrations'], 0)
