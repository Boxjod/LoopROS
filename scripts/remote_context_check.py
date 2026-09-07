#!/usr/bin/env python3
"""Read a remote project's small context record; never execute recorded commands."""
import argparse
import hashlib
import json
from pathlib import Path
import socket


def check(path):
    path = Path(path).resolve()
    if path.stat().st_size > 65536:
        raise ValueError('Context record too large')
    data = json.loads(path.read_text())
    if data.get('version') != 1:
        raise ValueError('Unsupported context version')
    root = path.parent.parent
    changed = []
    files = data['files']
    if not isinstance(files, dict) or not 1 <= len(files) <= 64:
        raise ValueError('Expected a bounded file fingerprint map')
    for name, digest in files.items():
        target = (root / name).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError('Tracked path leaves project') from None
        if Path(name).is_absolute():
            raise ValueError('Tracked path leaves project')
        if not target.is_file():
            changed.append({'path':name, 'reason':'missing'})
        elif target.stat().st_size > 8 * 1024 * 1024:
            changed.append({'path':name, 'reason':'size_limit'})
        elif hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            changed.append({'path':name, 'reason':'content_changed'})
    identity_matches = socket.gethostname() == data['connection']['observed_hostname'] and str(root) == data['project_root']
    return {'project_root':str(root), 'identity_matches':identity_matches,
            'tracked_files_match':not changed, 'changed':changed,
            'entries':data.get('entries', []),
            'last_verified_startup':data.get('last_verified_startup'),
            'current_readiness':'not_checked',
            'notice':'Historical data only. Matching tracked files is not readiness or permission; untracked dependencies may have changed.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', type=Path, default=Path(__file__).with_name('context.json'))
    args = parser.parse_args()
    result = check(args.context)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['identity_matches'] and result['tracked_files_match'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
