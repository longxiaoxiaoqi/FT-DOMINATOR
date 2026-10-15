"""Back up the production Compose stack and verify an independent host copy."""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from backup import verify


BASE = Path(__file__).resolve().parent


def run_compose(arguments):
    return subprocess.run(
        ['docker', 'compose', '--env-file', 'deploy.env', '-f',
         'compose.production.yaml', *arguments], cwd=BASE,
        check=True, text=True, capture_output=True).stdout.strip()


def backup_stack(destination, run=run_compose):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Lock survives a hard crash; the operator must check the service before removing it.
    lock = BASE / '.compose-backup.lock'
    with lock.open('x', encoding='utf-8') as stream:
        stream.write(str(os.getpid()))
    try:
        run(['config', '--quiet'])
        if not run(['ps', '--status', 'running', '-q', 'ft']).strip():
            raise ValueError('Application is not running; no service state was changed.')
        try:
            run(['stop', 'ft'])
            output = run(['run', '--rm', '--no-deps', '-T', 'ft', 'python', 'backup.py'])
            name = output.splitlines()[-1] if output else ''
            if not re.fullmatch(r'/data/backups/\d{8}-\d{6}-\d{6}Z', name):
                raise ValueError('Backup command did not return a valid backup path.')
        finally:
            # Also attempted after stop/backup failure or a keyboard interrupt.
            run(['start', 'ft'])
        # Application is running again before the potentially slow host copy.
        with tempfile.TemporaryDirectory(prefix='.copy-', dir=destination) as temp:
            copied = Path(temp) / 'snapshot'
            run(['cp', 'ft:' + name, str(copied)])
            verify(copied)
            target = destination / Path(name).name
            if target.exists():
                raise ValueError('Host backup destination already exists.')
            copied.rename(target)
        return target
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, type=Path,
                        help='Protected host backup directory, preferably on a separate mounted disk')
    args = parser.parse_args()
    try:
        print(backup_stack(args.destination))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        # Do not echo container output which may contain sensitive information.
        print('Backup failed: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
