# SPDX-FileCopyrightText: 2026 Nextcloud GmbH and Nextcloud contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare pinned upstream build tools and record the applied ARM64 patches."""
import configparser
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from arm64_config import TARGET, configure

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
PINS_FILE = ROOT / '.github/arm64-pins.json'


def run(*args, cwd=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def git(directory, *args):
    return subprocess.check_output(
        ['git', '-C', str(directory), *args], text=True, encoding='utf-8'
    ).strip()


def load_pins():
    pins = json.loads(PINS_FILE.read_text(encoding='utf-8'))
    allowed = {
        'source': 'https://github.com/nextcloud/desktop.git',
        'craft': 'https://github.com/nextcloud/craft.git',
        'craftmaster': 'https://github.com/KDE/craftmaster.git',
        'craft-blueprints-kde': 'https://github.com/nextcloud/craft-blueprints-kde.git',
        'craft-blueprints-nextcloud': 'https://github.com/nextcloud/craft-blueprints-nextcloud.git',
    }
    for name, url in allowed.items():
        pin = pins[name]
        if pin['url'] != url or len(pin['revision']) != 40 or any(c not in '0123456789abcdef' for c in pin['revision']):
            raise ValueError(f'Invalid upstream pin: {name}')
    return pins


def verify_source(directory, revision):
    # All build additions live under .github; every other tracked file must
    # match the official release, including packaging and CMake sources.
    subprocess.run([
        'git', '-C', str(directory), 'diff', '--exit-code', revision,
        '--', '.', ':(exclude).github',
    ], check=True)


def clone_pin(directory, pin):
    if not directory.exists():
        run('git', 'init', directory)
        run('git', '-C', directory, 'remote', 'add', 'origin', pin['url'])
        run('git', '-C', directory, 'fetch', '--depth', '1', 'origin', pin['revision'])
        run('git', '-C', directory, 'checkout', '--detach', 'FETCH_HEAD')
    if git(directory, 'remote', 'get-url', 'origin') != pin['url']:
        raise ValueError(f'Unexpected upstream remote: {directory}')
    return git(directory, 'rev-parse', 'HEAD')


def patch_script(name, *args):
    run(sys.executable, SCRIPTS / name, *args)


def patch_craft(directory):
    paths = [
        'bin/CraftSetupHelper.py', 'blueprints/dev-utils/_windows/git/git.py',
        'blueprints/dev-utils/perl/perl.py', 'blueprints/libs/openssl/openssl.py',
        'blueprints/libs/liblzma/liblzma.py', 'blueprints/libs/libunistring/libunistring.py',
        'blueprints/libs/libffi/libffi.py', 'blueprints/libs/python/python.py',
    ]
    patch_script('patch-craft-arm64.py', *(directory / path for path in paths))
    patch_script('patch_arm64_resources.py', directory)
    patch_script('patch_runtime_arm64.py', directory / 'blueprints/libs/runtime/runtime.py')
    patch_script('patch_msvc_toolset_arm64.py', directory / 'bin/CraftCompiler.py')
    patch_script('patch_download_retry_arm64.py', directory / 'bin/Utils/GetFiles.py')
    patch_script('patch-nsis-and-blueprint.py', directory)


def patch_blueprints(craft, kde, nextcloud):
    patch_script('patch-nsis-and-blueprint.py', craft, nextcloud / 'nextcloud-client/nextcloud-client.py')
    patch_script('patch-kde-blueprints-arm64.py',
                 kde / 'libs/libjpeg-turbo/libjpeg-turbo.py',
                 kde / 'libs/pixman/pixman.py',
                 nextcloud / 'libs/libp11/libp11.py',
                 kde / 'libs/qt6/qttools/qttools.py',
                 nextcloud / 'nextcloud-client/nextcloud-client.py')


def commit_patch(directory):
    if git(directory, 'status', '--porcelain'):
        run('git', '-C', directory, 'add', '-A')
        run('git', '-C', directory, '-c', 'user.name=ARM64 local build',
            '-c', 'user.email=arm64-build@users.noreply.github.com', 'commit',
            '-m', 'build: apply Windows ARM64 compatibility fixes\n\nAssisted-by: Codex:GPT-6')
    return git(directory, 'rev-parse', 'HEAD')


def write_config(path, craft_revision, blueprint_revisions):
    text = configure((ROOT / 'craftmaster.ini').read_text(encoding='utf-8-sig'),
                     craft_revision, str(Path(sys.executable).parent))
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read_string(text)
    for name, revision in blueprint_revisions.items():
        config['BlueprintSettings'][f'craft/{name}.revision'] = revision
    output = io.StringIO()
    config.write(output)
    path.write_text(output.getvalue(), encoding='utf-8', newline='\n')


def prepare(pins):
    craft = ROOT / 'craft-clone'
    head = clone_pin(craft, pins['craft'])
    if head == pins['craft']['revision']:
        patch_craft(craft)
        head = commit_patch(craft)
    elif git(craft, 'rev-parse', 'HEAD^') != pins['craft']['revision']:
        raise ValueError('Cached Craft does not derive directly from the pinned revision')
    master = ROOT / 'CraftMaster'
    if clone_pin(master, pins['craftmaster']) != pins['craftmaster']['revision']:
        raise ValueError('Unexpected CraftMaster revision')
    config = ROOT / 'craftmaster-arm64.ini'
    names = ('craft-blueprints-kde', 'craft-blueprints-nextcloud')
    write_config(config, head, {name: pins[name]['revision'] for name in names})
    locations = ROOT / TARGET / 'etc/blueprints/locations'
    for name in names:
        directory = locations / name
        pin = pins[name]
        if not (directory / '.git').exists():
            run(sys.executable, master / 'CraftMaster.py', '--config', config,
                '--target', TARGET, '-c', '--add-blueprint-repository',
                f"{pin['url']}||{pin['revision']}")
        if git(directory, 'remote', 'get-url', 'origin') != pin['url']:
            raise ValueError(f'Unexpected blueprint remote: {name}')
        run('git', '-C', directory, 'merge-base', '--is-ancestor', pin['revision'], 'HEAD')
    patch_blueprints(craft, locations / names[0], locations / names[1])
    revisions = {name: commit_patch(locations / name) for name in names}
    write_config(config, head, revisions)
    output = ROOT / 'release-output'
    output.mkdir(exist_ok=True)
    tools = {'craft': (craft, head), 'craftmaster': (master, pins['craftmaster']['revision'])}
    tools.update({name: (locations / name, revisions[name]) for name in names})
    manifests = {}
    for name, (directory, revision) in tools.items():
        diff = subprocess.check_output(['git', '-C', str(directory), 'diff', '--binary',
                                        pins[name]['revision'], revision])
        (output / f'{name}-arm64.patch').write_bytes(diff)
        manifests[name] = {'upstream': pins[name], 'patched_revision': revision,
                           'patch_sha256': hashlib.sha256(diff).hexdigest()}
    manifest = {'source': pins['source'], 'build_commit': git(ROOT, 'rev-parse', 'HEAD'),
                'tools': manifests, 'reference': pins['reference'], 'target': 'ARM64',
                'runner': os.environ.get('ImageVersion', 'unknown'),
                'python': sys.version, 'binary_dependency_cache': False}
    (output / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (output / 'craftmaster-arm64.ini').write_bytes(config.read_bytes())


if __name__ == '__main__':
    pins = load_pins()
    if len(sys.argv) == 2 and sys.argv[1] == 'verify':
        # Fetch from official upstream even when the fork already has the object.
        run('git', '-C', ROOT, 'fetch', '--depth', '1', pins['source']['url'], pins['source']['revision'])
        verify_source(ROOT, pins['source']['revision'])
        upstream = configparser.ConfigParser(interpolation=None)
        upstream.read(ROOT / 'craftmaster.ini', encoding='utf-8')
        if upstream['General']['CraftRevision'] != pins['craft']['revision'] or upstream['General']['CraftUrl'] != pins['craft']['url']:
            raise ValueError('Craft pin does not match the official source configuration')
        print('Official release source verified; build additions are confined to .github.')
    elif len(sys.argv) == 2 and sys.argv[1] == 'prepare':
        prepare(pins)
    else:
        raise SystemExit('Usage: arm64_prepare.py verify|prepare')
