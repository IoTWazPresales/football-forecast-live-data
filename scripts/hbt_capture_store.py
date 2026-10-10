"""Resolve an immutable refreshed capture without rewriting the original card."""
import hashlib
import json
from pathlib import Path


def capture_path(root, target):
    root = Path(root)
    pointer = root / f'hbt_current_capture_{target}.json'
    if not pointer.exists():
        return root / f'hbt_prospective_card_{target}.json'
    manifest = json.loads(pointer.read_text())
    relative = Path(manifest.get('path') or '')
    if (manifest.get('targetDate') != target or relative.is_absolute() or '..' in relative.parts
            or len(relative.parts) != 2 or relative.parts[0] != 'captures'
            or not relative.name.startswith(f'hbt_prospective_card_{target}_')):
        raise ValueError('invalid current capture pointer; cannot fall back silently')
    path = root / relative
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest.get('sha256'):
        raise ValueError('immutable refreshed capture hash mismatch')
    doc = json.loads(raw)
    if doc.get('targetDate') != target or (doc.get('policy') or {}).get('preMatchCaptureImmutable') is not True:
        raise ValueError('invalid refreshed capture identity/policy')
    return path
