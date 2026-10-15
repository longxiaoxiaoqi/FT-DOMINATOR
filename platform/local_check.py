"""Read-only local diagnostics. Never reads passwords, keys or business rows."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.request

from ft.build import BASE, BUILD_ID, INSTANCE_ID


def check_data(root):
    database = root / 'ft.sqlite3'
    if not database.is_file():
        raise ValueError('Local database does not exist. Run start.bat for initial setup.')
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        integrity = db.execute('PRAGMA quick_check').fetchall() == [('ok',)]
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'core_attachment', 'core_taskattachment', 'django_migrations', 'auth_user'}
        if not required <= tables:
            raise ValueError('Local database structure is incomplete. Check migrations before starting.')
        applied = {row[0] for row in db.execute("SELECT name FROM django_migrations WHERE app='core'")}
        expected = {path.stem for path in (BASE / 'core/migrations').glob('[0-9]*.py')}
        missing, unsafe = 0, 0
        uploads = (root / 'uploads').resolve()
        for table in ('core_attachment', 'core_taskattachment'):
            for (stored,) in db.execute('SELECT stored_name FROM ' + table):
                path = (uploads / stored).resolve()
                if not path.is_relative_to(uploads):
                    unsafe += 1
                elif not path.is_file():
                    missing += 1
    return {'database_integrity': integrity, 'missing_attachments': missing,
            'unsafe_attachment_paths': unsafe, 'pending_core_migrations': len(expected - applied)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Check data without contacting the local service')
    parser.add_argument('--port', type=int, default=int(os.environ.get('FT_PORT', '4180')))
    args = parser.parse_args()
    root = Path(os.environ.get('FT_DATA_DIR', BASE / 'runtime')).resolve()
    try:
        result = check_data(root)
        result['expected_build'] = BUILD_ID
        if not args.offline:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/session', timeout=3) as response:
                session = json.load(response)
            result.update(service_available=session.get('app') == 'ft-platform',
                          service_build_current=session.get('build') == BUILD_ID,
                          service_data_directory_current=session.get('instance') == INSTANCE_ID)
        good = (result['database_integrity'] and not result['missing_attachments']
                and not result['unsafe_attachment_paths'] and not result['pending_core_migrations']
                and (args.offline or all(result[key] for key in (
                    'service_available', 'service_build_current', 'service_data_directory_current'))))
        result['ok'] = bool(good)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if good else 1
    except (OSError, ValueError, sqlite3.Error, urllib.error.URLError) as error:
        print('Local check failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
