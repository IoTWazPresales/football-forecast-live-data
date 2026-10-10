#!/usr/bin/env python3
"""Publish staged generated HBT output without clobbering a concurrent branch advance.

Only disjoint upstream changes can be replayed. Conflicting output, immutable
capture edits, parameter changes and broken desk provenance fail closed. The
original runner worktree is retained; no force push or cleanup is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

BRANCH = 'research/hbt-1.4-match-intelligence'
PARAMS = {'event_model_params.json', 'player_prop_model_params.json'}


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()


def publish(message, remote='origin'):
    paths = git('diff', '--cached', '--name-only').splitlines()
    if not paths:
        return 'NO_CHANGES'
    for name in paths:
        path = Path(name)
        if not name.startswith('hbt_live_data/') or path.name in PARAMS:
            raise ValueError('publication allows generated HBT output only: ' + name)
        if path.name.startswith('hbt_prospective_card_'):
            original = subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + name], capture_output=True)
            if original.returncode == 0:
                raise ValueError('cannot edit an existing immutable prospective capture: ' + name)
    base = git('rev-parse', 'HEAD')
    git('fetch', remote, BRANCH)
    upstream = git('rev-parse', 'FETCH_HEAD')
    if subprocess.run(['git', 'merge-base', '--is-ancestor', base, upstream], capture_output=True).returncode:
        raise ValueError('upstream is not a descendant of the checked-out research revision')
    overlap = set(paths) & set(git('diff', '--name-only', base, upstream).splitlines())
    if overlap:
        raise ValueError('concurrent HBT output changed; preserve artifact and rerun on latest inputs: ' + ', '.join(sorted(overlap)))
    tree = git('write-tree')
    commit = git('commit-tree', tree, '-p', base, '-m', message)
    with tempfile.TemporaryDirectory(prefix='hbt-publish-') as directory:
        workspace = Path(directory) / 'review'
        git('worktree', 'add', '--detach', str(workspace), commit)
        try:
            git('rebase', upstream, cwd=workspace)
            for name in paths:
                if not (Path(name).name.startswith('hbt_betting_desk_') and name.endswith('.json')):
                    continue
                doc = json.loads((workspace / name).read_text())
                files = doc.get('sourceFiles') or {}
                for key, digest in (doc.get('sourceHashes') or {}).items():
                    relative = Path(files[key])
                    if relative.is_absolute() or '..' in relative.parts:
                        raise ValueError('desk source path must remain inside HBT data')
                    source = workspace / 'hbt_live_data' / relative
                    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                        raise ValueError('desk input changed during publication: ' + str(relative))
            git('push', remote, 'HEAD:' + BRANCH, cwd=workspace)
            return git('rev-parse', 'HEAD', cwd=workspace)
        finally:
            git('worktree', 'remove', '--force', str(workspace))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--message', required=True); args = ap.parse_args()
    try:
        print(publish(args.message))
    except (ValueError, subprocess.CalledProcessError, KeyError, OSError) as exc:
        raise SystemExit(f'HBT output not published; runner evidence retained: {exc}')


if __name__ == '__main__':
    main()
