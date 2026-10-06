import argparse
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import stat
import subprocess
import sys


EXCLUDED = {'.git', '.DS_Store', '.debris', '.megaignore'}


def check_root(root: Path) -> None:
    if not root.is_dir():
        raise RuntimeError(f'Missing sync folder: {root}')
    if root.stat().st_flags & stat.SF_DATALESS:
        raise RuntimeError(f'iCloud folder is not downloaded: {root}. Use Finder > Keep Downloaded, then retry.')
    count = 0

    def walk_error(error: OSError) -> None:
        raise error

    for directory, folders, files in os.walk(root, onerror=walk_error):
        folders[:] = [name for name in folders if name not in EXCLUDED]
        for name in folders + files:
            if name in EXCLUDED:
                continue
            path = Path(directory) / name
            info = path.lstat()
            if name.endswith('.icloud') or info.st_flags & stat.SF_DATALESS:
                raise RuntimeError(
                    f'iCloud item is not downloaded: {path}. '
                    'Use Finder > Keep Downloaded on the iCloud vault folder, then retry.'
                )
            if stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                count += 1
    if not count:
        raise RuntimeError(f'Refusing to sync an empty folder: {root}')


def command(binary: Path, local: Path, cloud: Path, state: Path) -> list[str]:
    return [
        str(binary), str(local), str(cloud),
        '-ui', 'text', '-batch', '-dumbtty', '-color', 'false',
        '-fastcheck', 'false', '-confirmbigdel=true',
        '-perms', '0', '-dontchmod', '-times',
        '-backup', 'Name *', '-backuploc', 'central',
        '-backupdir', str(state / 'backups'), '-maxbackups', '10',
        '-log=false',
        *[part for name in sorted(EXCLUDED) for part in ('-ignore', f'Name {name}')],
        '-ignore', 'Name *.icloud',
    ]


def synchronize(local: Path, cloud: Path, state: Path, binary: Path,
                log: logging.Logger, check: bool = False, lock_fd: int | None = None) -> int:
    if not hasattr(stat, 'SF_DATALESS'):
        raise RuntimeError('This tool requires macOS with iCloud file flag support.')
    if local == cloud or local in cloud.parents or cloud in local.parents:
        raise RuntimeError('Sync folders must be separate and cannot contain each other.')
    if state == local or state == cloud or local in state.parents or cloud in state.parents:
        raise RuntimeError('Sync state must be stored outside both vault folders.')
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError(f'Unison executable is missing: {binary}')
    log.info('Checking local folder: %s', local)
    check_root(local)
    log.info('Checking iCloud folder: %s', cloud)
    check_root(cloud)
    archive = state / 'archives'
    marker = state / 'initialized'
    if marker.exists():
        saved = marker.read_text()
        if saved.startswith('{'):
            try:
                history = json.loads(saved)
            except json.JSONDecodeError as error:
                raise RuntimeError('Sync history marker is invalid. Restore it before synchronizing.') from error
            roots = history.get('roots')
            archives = history.get('archives', [])
            if (not isinstance(archives, list) or len(archives) != 2
                    or any(not isinstance(name, str) or Path(name).name != name
                           or not (archive / name).is_file() for name in archives)):
                raise RuntimeError('Sync history is missing. Restore the archives before synchronizing.')
        else:
            roots = saved.splitlines()
            archives = list(archive.glob('ar*'))
            if len(archives) != 2 or any(not path.is_file() for path in archives):
                raise RuntimeError('Sync history is missing. Restore the archives before synchronizing.')
        if roots != [str(local), str(cloud)]:
            raise RuntimeError('The folders differ from the saved sync history. Use a separate state directory.')
    if check:
        log.info('Preflight passed. Vault files were not changed.')
        return 0
    archive.mkdir(parents=True, exist_ok=True, mode=0o700)
    (state / 'backups').mkdir(exist_ok=True, mode=0o700)
    if not marker.exists():
        log.warning('First run: files present on only one side are kept; earlier deletions cannot be inferred.')
    environment = {**os.environ, 'UNISON': str(archive), 'LC_ALL': 'en_US.UTF-8',
                   'UNISONLOCALHOSTNAME': 'obsidian-sync'}
    environment.pop('UNISONBACKUPDIR', None)
    log.info('Sync started: %s <-> %s', local, cloud)
    with subprocess.Popen(command(binary, local, cloud, state), env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, text=True, errors='replace',
                          pass_fds=(lock_fd,) if lock_fd is not None else ()) as process:
        for line in process.stdout:
            log.info('%s', line.rstrip())
        result = process.wait()
    if result in (0, 1):
        names = sorted(path.name for path in archive.glob('ar*') if path.is_file())
        if len(names) != 2:
            raise RuntimeError('Expected two sync archives after synchronization; history was not saved.')
        pending = marker.with_suffix('.tmp')
        pending.write_text(json.dumps({'roots': [str(local), str(cloud)], 'archives': names}) + '\n')
        pending.replace(marker)
    if result == 0:
        log.info('Sync completed successfully.')
    elif result == 1:
        log.warning('Sync has unresolved conflicts or skipped files. Both versions are preserved; see details above.')
    else:
        log.error('Sync failed with Unison exit code %s.', result)
    return result


def main() -> int:
    home = Path.home()
    parser = argparse.ArgumentParser(description='Synchronize Obsidian vaults in both directions using Unison.')
    parser.add_argument('--local', type=Path, default=home / 'Documents/OBSIDIAN_VAULTS')
    parser.add_argument('--icloud', type=Path,
                        default=home / 'Library/Mobile Documents/iCloud~md~obsidian/Documents')
    parser.add_argument('--state-dir', type=Path, default=home / '.local/state/obsidian-sync')
    parser.add_argument('--unison', type=Path,
                        default=home / '.local/share/obsidian-sync/unison-2.54.0')
    parser.add_argument('--log-file', type=Path, default=home / 'Library/Logs/obsidian-sync.log')
    parser.add_argument('--check', action='store_true', help='Check availability without synchronizing vault files.')
    args = parser.parse_args()
    log = logging.getLogger('obsidian-sync')
    log.setLevel(logging.INFO)
    log.handlers.clear()
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(stream)
    try:
        state = args.state_dir.expanduser().resolve()
        local = args.local.expanduser().resolve()
        cloud = args.icloud.expanduser().resolve()
        if state == local or state == cloud or local in state.parents or cloud in state.parents:
            raise RuntimeError('Sync state must be stored outside both vault folders.')
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (state / 'lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log.info('Another sync is running; this invocation was skipped.')
                return 0
            args.log_file.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(args.log_file, maxBytes=5_000_000, backupCount=3)
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            log.addHandler(handler)
            return synchronize(local, cloud, state, args.unison.expanduser(), log,
                               args.check, lock.fileno())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        log.error('%s', error)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
