"""Source fingerprint captured once per process, without reading runtime secrets."""
import hashlib
import json
import os
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent


def source_build(base=BASE):
    paths = [base / name for name in ('manage.py', 'serve.py', 'requirements.txt')]
    for folder in ('ft', 'core', 'static', 'templates'):
        paths.extend(p for p in (base / folder).rglob('*')
                     if p.is_file() and p.suffix in {'.py', '.js', '.css', '.html'}
                     and '__pycache__' not in p.parts and not p.name.startswith('test'))
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(base).as_posix().encode('utf-8') + b'\0')
        digest.update(path.read_bytes() + b'\0')
    return digest.hexdigest()[:16]


def instance_id(base=BASE):
    runtime = Path(os.environ.get('FT_DATA_DIR', base / 'runtime')).resolve()
    return hashlib.sha256((os.path.normcase(str(base.resolve())) + '\0' +
                           os.path.normcase(str(runtime))).encode('utf-8')).hexdigest()[:16]


BUILD_ID = source_build()
INSTANCE_ID = instance_id()

if __name__ == '__main__':
    print(json.dumps({'build': BUILD_ID, 'instance': INSTANCE_ID}))
