# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reuse the first build's cache only when its dependency build is unchanged."""
from pathlib import Path
import re
import subprocess
import sys

BASELINE = '681512a398e9743a6c02b7de7dfa5d2b0979fa8b'
WORKFLOW = '.github/workflows/arm64-release.yml'
ROOT = Path(__file__).resolve().parents[2]


def build_plan(workflow):
    pattern = r'(?ms)^      - name: Fingerprint the dependency build inputs\n.*?(?=^      - (?:name:|uses:)|\Z)'
    result, count = re.subn(pattern, '', workflow.replace('\r\n', '\n'))
    if count != 1:
        raise ValueError('Expected one dependency fingerprint step')
    return result


def compatible_changes(changed_paths, previous_workflow, current_workflow):
    allowed = {
        WORKFLOW, '.github/scripts/arm64_verify.py',
        '.github/scripts/arm64_cache_recovery.py', '.github/ARM64-BUILD.txt',
        '.github/arm64-cache-recovery.txt',
    }
    for path in changed_paths:
        if path not in allowed and not path.startswith('.github/scripts/tests/'):
            return False
    return build_plan(previous_workflow) == build_plan(current_workflow)


def select_fingerprint(current, saved, directory=ROOT):
    for value in (current, saved):
        if not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('Expected a complete SHA-256 cache fingerprint')
    changed = subprocess.check_output(
        ['git', '-C', str(directory), 'diff', '--name-only', BASELINE], text=True
    ).splitlines()
    previous = subprocess.check_output(
        ['git', '-C', str(directory), 'show', f'{BASELINE}:{WORKFLOW}'], text=True
    )
    workflow = (directory / WORKFLOW).read_text(encoding='utf-8-sig')
    return saved if compatible_changes(changed, previous, workflow) else current


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: arm64_cache_recovery.py <current-fingerprint> <saved-fingerprint>')
    print(select_fingerprint(sys.argv[1], sys.argv[2]))
