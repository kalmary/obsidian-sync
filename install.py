from datetime import datetime
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys


def install(project: Path, uv: str, python: str) -> None:
    home = Path.home()
    executable = home / '.local/bin/obsidian-sync'
    tools = home / '.local/share/uv/tools/obsidian-sync-python'
    if executable.exists() or executable.is_symlink():
        if not tools.is_dir() or not executable.is_symlink() or tools not in executable.resolve().parents:
            raise RuntimeError(f'An unrelated command already exists: {executable}')
    binary = project / 'vendor/unison'
    subprocess.run([str(binary), '-version'], check=True)
    environment = {**os.environ, 'UV_CACHE_DIR': '/private/tmp/obsidian-sync-uv-cache'}
    subprocess.run([uv, 'tool', 'install', '--reinstall', '--python', python, str(project)],
                   check=True, env=environment)
    runtime = home / '.local/share/obsidian-sync'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copy2(binary, runtime / 'unison-2.54.0')
    shutil.copy2(project / 'vendor/UNISON-LICENSE', runtime / 'UNISON-LICENSE')
    subprocess.run([str(executable), '--help'], check=True, stdout=subprocess.DEVNULL)
    zshrc = home / '.zshrc'
    original = zshrc.read_text()
    replacement = 'obsidian-sync() {\n    "$HOME/.local/bin/obsidian-sync" "$@"\n}'
    updated, matches = re.subn(r'(?m)^obsidian-sync\(\) \{\n.*?^\}',
                               lambda _: replacement, original, flags=re.DOTALL)
    if matches != 1:
        raise RuntimeError('Expected exactly one obsidian-sync function in .zshrc; installation stopped.')
    plist = home / 'Library/LaunchAgents/pl.michalsiniarski.obsidian-sync.plist'
    script = home / '.local/bin/sync-obsidian.sh'
    backup = runtime / ('migration-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(mode=0o700)
    for path in (zshrc, plist, script):
        if path.exists():
            shutil.copy2(path, backup / path.name)
    job = f'gui/{os.getuid()}/pl.michalsiniarski.obsidian-sync'
    domain = f'gui/{os.getuid()}'
    lock = Path(f'/tmp/obsidian-sync-{os.getuid()}.lock')
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as error:
        raise RuntimeError('The old sync is running or has a leftover lock. Resolve that before retrying.') from error
    loaded = subprocess.run(['launchctl', 'print', job], capture_output=True).returncode == 0
    try:
        if loaded:
            subprocess.run(['launchctl', 'bootout', job], check=True)
        zshrc.write_text(updated)
        subprocess.run(['/bin/zsh', '-n', str(zshrc)], check=True)
        script.write_text('#!/bin/bash\nset -euo pipefail\nexec "$HOME/.local/bin/obsidian-sync" "$@"\n')
        script.chmod(0o755)
        config = {
            'Label': 'pl.michalsiniarski.obsidian-sync',
            'ProgramArguments': [str(executable)],
            'RunAtLoad': True,
            'StartInterval': 7200,
            'StandardOutPath': '/dev/null',
            'StandardErrorPath': str(home / 'Library/Logs/obsidian-sync-launchd-error.log'),
        }
        plist.write_bytes(plistlib.dumps(config))
        subprocess.run(['/usr/bin/plutil', '-lint', str(plist)], check=True)
        subprocess.run(['launchctl', 'bootstrap', domain, str(plist)], check=True)
    except BaseException:
        subprocess.run(['launchctl', 'bootout', job], capture_output=True)
        for path in (zshrc, plist, script):
            saved = backup / path.name
            if saved.exists():
                shutil.copy2(saved, path)
        if loaded:
            subprocess.run(['launchctl', 'bootstrap', domain, str(plist)], check=False)
        raise
    finally:
        lock.rmdir()
    print(f'Installed obsidian-sync. Configuration backup: {backup}')


if __name__ == '__main__':
    install(Path(sys.argv[1]).resolve(), sys.argv[2], sys.argv[3])
