"""Reconcile lock exclusion metadata only; never resolve or install packages."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
import tempfile
import tomllib


HEADER = b'[options.exclude-newer-package]\n'
LIMIT = 5 * 1024 * 1024


def normalize(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', name):
        raise ValueError('Invalid package name')
    return re.sub(r'[-_.]+', '-', name).lower()


def option_map(values):
    result = {}
    for key, value in values.items():
        name = normalize(key)
        if name in result:
            raise ValueError('Ambiguous exclusion aliases: ' + name)
        result[name] = value
    return result


def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMIT:
            raise ValueError('Expected bounded regular file without links: ' + path.name)
        raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError('Input exceeds metadata size bound')
        return raw, info


def reconcile(root):
    root = pathlib.Path(root)
    project_path, lock_path = root / 'pyproject.toml', root / 'uv.lock'
    project_raw, _ = read_regular(project_path)
    original, info = read_regular(lock_path)
    project = tomllib.loads(project_raw.decode('utf-8'))
    lock = tomllib.loads(original.decode('utf-8'))
    if type(lock.get('version')) is not int or lock['version'] != 1 or type(lock.get('revision')) is not int or lock['revision'] != 3:
        raise ValueError('Unsupported lock schema; manual review required')
    declared = option_map(project['tool']['uv']['exclude-newer-package'])
    recorded = option_map(lock['options']['exclude-newer-package'])
    for name, value in recorded.items():
        if name not in declared or type(declared[name]) is not type(value) or declared[name] != value:
            raise ValueError('Changed or removed exclusion needs manual review: ' + name)
    missing = sorted(declared.keys() - recorded.keys())
    packages = {normalize(p['name']) for p in lock['package']}
    for name in missing:
        if declared[name] is not False or name not in packages:
            raise ValueError('Only explicit false exclusions for already locked packages may be added: ' + name)
    updated = original
    if missing:
        if original.count(HEADER) != 1:
            raise ValueError('Unsupported lock table representation')
        lines = ''.join(f'{name} = false\n' for name in missing).encode()
        updated = original.replace(HEADER, HEADER + lines, 1)
        after = tomllib.loads(updated.decode('utf-8'))
        for name in missing:
            if after['options']['exclude-newer-package'].pop(name) is not False:
                raise ValueError('Unexpected reconciliation value')
        if after != lock:
            raise ValueError('Reconciliation changed data outside added exclusions')
        # No untrusted process runs during this preparation step. Re-read before
        # atomic replacement to reject accidental input changes, not follow links.
        if read_regular(project_path)[0] != project_raw or read_regular(lock_path)[0] != original:
            raise ValueError('Metadata changed during reconciliation')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=root, prefix='.bridge-lock-', delete=False) as stream:
                temporary = pathlib.Path(stream.name)
                os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
                stream.write(updated)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, lock_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {'schema': 1, 'added_exclusions': missing,
            'lock_before_sha256': hashlib.sha256(original).hexdigest(),
            'lock_after_sha256': hashlib.sha256(updated).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = reconcile(args.repository)
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        print('LOCK_METADATA_REFUSED: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
