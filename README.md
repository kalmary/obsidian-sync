This project was written with AI assistance and tested with automated integration
tests using temporary vaults and the real Unison engine. It is designed for safe
synchronization: conflicting versions are preserved, overwritten or deleted files
are backed up, and checks reject unavailable folders and missing sync history.
These safeguards reduce the risk of data loss; keep an independent vault backup.

# obsidian-sync-python

Bidirectional synchronization between local Obsidian vaults and their iCloud
copies on a Mac. Python handles availability checks, logging, process locking,
and exit codes; Unison 2.54.0 tracks changes and synchronizes files.

| Replica | Default folder |
| --- | --- |
| Local | `~/Documents/OBSIDIAN_VAULTS` |
| iCloud | `~/Library/Mobile Documents/iCloud~md~obsidian/Documents` |

The tool synchronizes files currently visible on this Mac. It cannot confirm
that iCloud has uploaded them or received changes from other devices.

## Requirements

- macOS on Apple Silicon for the bundled Unison executable.
- Python 3.13 or newer and [uv](https://docs.astral.sh/uv/).
- Both vault folders must exist and contain at least one eligible file or symlink.
- The iCloud vault folder must be downloaded locally. Select **Keep Downloaded**
  in Finder before synchronizing.

There are no third-party Python runtime dependencies. The CLI requires macOS
iCloud file-flag support, even when custom folders are used.

## Installation

### Existing setup migration

```sh
./install.sh
```

This installer is intended for an existing setup: `~/.zshrc` must contain exactly
one multiline function starting with `obsidian-sync() {` and ending with `}` on
its own line. `~/Library/LaunchAgents` must also exist. If that shell function is
missing, use the manual installation below. The installer may already have
installed the Python package and copied Unison before reporting this error.

By default, the script uses `/opt/homebrew/bin/python3` and `~/.local/bin/uv`.
Override these paths with `OBSIDIAN_SYNC_PYTHON` and `OBSIDIAN_SYNC_UV` if needed.

The installer:

- Installs the command in a dedicated uv tool environment.
- Copies Unison and its license to `~/.local/share/obsidian-sync/`.
- Backs up the existing shell configuration, launch-agent plist, and legacy
  wrapper, when present, under `~/.local/share/obsidian-sync/migration-*`.
- Updates the shell function and `~/.local/bin/sync-obsidian.sh` wrapper.
- Loads `~/Library/LaunchAgents/pl.michalsiniarski.obsidian-sync.plist`, scheduled
  to run at login and every two hours.

**Loading the launch agent starts synchronization immediately.** Back up your
vaults and download the iCloud folder before running the installer. It refuses
to replace an unrelated `obsidian-sync` command or proceed while the legacy
lock `/tmp/obsidian-sync-<uid>.lock` exists. Configuration changes are restored
from the migration backup if the launch-agent update fails.

### Manual installation

From the project directory:

```sh
uv tool install --python /opt/homebrew/bin/python3 .
mkdir -p ~/.local/share/obsidian-sync
cp vendor/unison ~/.local/share/obsidian-sync/unison-2.54.0
cp vendor/UNISON-LICENSE ~/.local/share/obsidian-sync/UNISON-LICENSE
~/.local/bin/obsidian-sync --check
```

This installs the CLI without modifying shell configuration or scheduling
automatic synchronization. Add `~/.local/bin` to your `PATH` to invoke it as
`obsidian-sync`.

To reinstall the Python package after changing its source:

```sh
uv tool install --reinstall --python /opt/homebrew/bin/python3 .
```

## Usage

```sh
obsidian-sync --check
obsidian-sync
obsidian-sync --help
```

`--check` validates folder availability, engine availability, and saved history
without changing vault files or running Unison. It still creates the state/lock
and log files as needed; it does not preview individual changes or conflicts.

For a different pair of vaults:

```sh
obsidian-sync \
  --local ~/Documents/MyVault \
  --icloud "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault" \
  --state-dir ~/.local/state/obsidian-sync-my-vault
```

Use a separate state directory for each pair of roots. Local and iCloud roots
must be separate and cannot contain each other; state must be outside both.

| Option | Default |
| --- | --- |
| `--local` | `~/Documents/OBSIDIAN_VAULTS` |
| `--icloud` | `~/Library/Mobile Documents/iCloud~md~obsidian/Documents` |
| `--state-dir` | `~/.local/state/obsidian-sync` |
| `--unison` | `~/.local/share/obsidian-sync/unison-2.54.0` |
| `--log-file` | `~/Library/Logs/obsidian-sync.log` |
| `--check` | Availability/history checks only |

## Synchronization behavior

On the first run, files present on only one side are treated as additions.
Deletions made before history was established cannot be reconstructed. After
that, additions, edits, and deletions propagate in either direction. Renames
are handled as deletions and additions.

Files are checked by content, so changes are detected even when modification
times are unchanged. Full-vault scans can take longer than timestamp-based
copies.

If a file is edited differently on both sides, or deleted on one side and edited
on the other, Unison leaves the conflicting states untouched and logs the
conflict. Unrelated changes can still synchronize. Resolve a conflict by making
both copies agree, then run the command again.

`.git`, `.DS_Store`, `.debris`, `.megaignore`, and `*.icloud` are excluded from
Unison transfers. The preflight check aborts if it finds an iCloud placeholder
outside excluded directories, rather than silently skipping undownloaded data.
Obsidian settings, including `.obsidian`, synchronize with the other files.
The application does not run Git commands.

## Safety and recovery

Synchronization stops before invoking Unison if a root is missing, empty, or
contains an undownloaded iCloud item. An entirely empty replica is therefore
not a supported way to delete every file on the other side. Unison is also
configured to require confirmation for large deletions, with batch mode enabled.
Avoid editing files during a sync, and retain an independent backup.

History is stored in `~/.local/state/obsidian-sync/archives`, with the root pair
and archive filenames recorded in `~/.local/state/obsidian-sync/initialized`.
Once initialized, missing expected archives or a changed root pair cause the
command to abort. Preserve the whole state directory; do not delete it to clear
conflicts, because history distinguishes additions from deletions.

Before replacing or deleting files, Unison keeps up to ten backup versions per
file under `~/.local/state/obsidian-sync/backups`. To restore a version, inspect
the backups and copy the chosen contents to both replicas before synchronizing.
These local backups do not replace a separate vault backup.

An operating-system lock skips overlapping invocations. The Unison child
inherits the lock, so it remains held if the Python parent exits while the
engine is still running. The OS releases it when its last owning process exits;
a leftover lock file alone does not block synchronization. Unison may retain
its own archive lock after interruption. Confirm that no engine is running
before following its lock-recovery instructions.

## Logs and exit codes

Progress is printed to the terminal and written to
`~/Library/Logs/obsidian-sync.log`. The log rotates at 5,000,000 bytes and retains
three previous copies. The installed launch agent writes standard errors to
`~/Library/Logs/obsidian-sync-launchd-error.log`.

| Code | Meaning |
| --- | --- |
| `0` | Successful sync/preflight, or an overlapping invocation was skipped |
| `1` | Conflicts or skipped updates |
| `2` | Failed safety check or synchronization error |
| `3` | Partial synchronization with transfer failures |

## Development and testing

```sh
uv sync
UNISON_BINARY="$PWD/vendor/unison" uv run python -m unittest discover -s tests -v
```

Without `UNISON_BINARY`, tests use the private installed engine at
`~/.local/share/obsidian-sync/unison-2.54.0`. Tests create isolated temporary vaults,
state, and logs; they do not synchronize your real vaults.

The 16 integration tests cover additions and edits in both directions, unchanged
timestamps, deletions, edit/edit and delete/edit conflicts, initial conflicts,
backups, Unicode directory renames, exclusions, missing/empty roots, iCloud
placeholder rejection, missing or substituted history archives, and process
locking, including a terminated parent with a surviving engine.

The suite validates the CLI and synchronization behavior. It does not exercise
the installer, launch-agent scheduling, or Apple's remote iCloud delivery.

## License

The Python application, installer, and original project files are licensed under
the [MIT License](LICENSE).

The bundled `vendor/unison` executable is separately licensed under the
[GNU GPL version 3](vendor/UNISON-LICENSE); the MIT license does not relicense it.
Unison source and release information are available from the
[upstream project](https://github.com/bcpierce00/unison).
