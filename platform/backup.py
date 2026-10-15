"""Stopped-service SQLite backups, verification and restore to a NEW directory."""
import argparse
from contextlib import closing
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


KEY_FILES = ('secret-key.txt', 'initial-setup.txt')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def files(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symbolic links are not supported in backups.')
        if path.is_file() and path != root / 'manifest.json':
            result[path.relative_to(root).as_posix()] = path
    return result


def check_database(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed.')


def verify(root):
    root = Path(root).resolve()
    manifest_path = root / 'manifest.json'
    if manifest_path.is_symlink():
        raise ValueError('Symbolic manifest is not supported.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unsupported backup manifest.')
    actual = files(root)
    expected = manifest['files']
    if 'ft.sqlite3' not in expected or set(actual) != set(expected):
        raise ValueError('Backup file list does not match manifest.')
    for name, path in actual.items():
        if name != 'ft.sqlite3' and name not in KEY_FILES and not name.startswith('uploads/'):
            raise ValueError('Unexpected backup file.')
        if expected[name] != {'size': path.stat().st_size, 'sha256': digest(path)}:
            raise ValueError('Backup checksum mismatch: ' + name)
    check_database(root / 'ft.sqlite3')
    return manifest


def create(root):
    root = Path(root).resolve()
    if not (root / 'ft.sqlite3').is_file():
        raise ValueError('Database does not exist.')
    if any((root / name).is_symlink() for name in ('ft.sqlite3', 'uploads', *KEY_FILES)):
        raise ValueError('Symbolic source paths are not supported.')
    if (root / 'uploads').exists():
        files(root / 'uploads')  # Reject links before copying.
    backups = root / 'backups'
    backups.mkdir(exist_ok=True)
    target = backups / datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%fZ')
    staging = Path(tempfile.mkdtemp(prefix='.incomplete-', dir=backups))
    try:
        with closing(sqlite3.connect((root / 'ft.sqlite3').as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(staging / 'ft.sqlite3')) as dst:
                src.backup(dst)
        if (root / 'uploads').exists():
            shutil.copytree(root / 'uploads', staging / 'uploads')
        for name in KEY_FILES:
            if (root / name).exists():
                shutil.copy2(root / name, staging / name)
        manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'files': {name: {'size': path.stat().st_size, 'sha256': digest(path)}
                              for name, path in files(staging).items()}}
        (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        verify(staging)
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return target


def restore(source, destination):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    verify(source)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Restore destination must not exist; existing data is never overwritten.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.restore-', dir=destination.parent))
    try:
        shutil.copytree(source, staging, dirs_exist_ok=True)
        verify(staging)
        # Keep the checksum manifest outside runtime: it describes this snapshot only.
        (staging / 'manifest.json').unlink()
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--verify', type=Path, metavar='BACKUP')
    action.add_argument('--restore', type=Path, metavar='BACKUP')
    parser.add_argument('--to', type=Path, metavar='NEW_DIRECTORY')
    args = parser.parse_args()
    if bool(args.restore) != bool(args.to):
        parser.error('--restore and --to must be used together')
    try:
        if args.verify:
            verify(args.verify)
            print('Backup verified.')
        elif args.restore:
            print(restore(args.restore, args.to))
        else:
            if os.environ.get('FT_POSTGRES_NAME'):
                raise ValueError('This tool supports SQLite only; use a PostgreSQL backup procedure.')
            print(create(Path(os.environ.get('FT_DATA_DIR', Path(__file__).resolve().parent / 'runtime'))))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
