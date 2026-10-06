# obsidian-sync-python

Bidirectional Obsidian synchronization between `~/Documents/OBSIDIAN_VAULTS`
and `~/Library/Mobile Documents/iCloud~md~obsidian/Documents`.

Python handles folder checks, logging, process locking and exit codes. Unison
2.54.0 tracks changes and performs synchronization. macOS on Apple Silicon and
Python 3.13 or newer are required. The supplied Unison executable is the official
macOS ARM64 command-line release; its license is in `vendor/UNISON-LICENSE`.

## Installation

Run `./install.sh`. This installs the command in a dedicated uv tool environment,
stores Unison outside PATH at `~/.local/share/obsidian-sync/unison-2.54.0`, updates
the existing zsh function and launch agent, and preserves configuration backups
under `~/.local/share/obsidian-sync/migration-*`. It does not install Python
packages into any other project environment. The launch agent runs at login
and every two hours. Reloading the agent starts its first run immediately.

The script stops if `obsidian-sync` belongs to another installed package.
To update this package after editing its source, run:

```sh
uv tool install --reinstall --python /opt/homebrew/bin/python3 .
```

## Usage

```sh
obsidian-sync
obsidian-sync --check
obsidian-sync --help
```

`--check` scans folder availability and saved history without changing vault
files. Logs are written to `~/Library/Logs/obsidian-sync.log`, with three rotated
copies of up to 5 MB each. The command also prints progress to the terminal.

On the first run, files present on only one side are treated as additions.
Earlier deletions cannot be reconstructed from the old script. Once history
has been established, deletions, additions and edits propagate in either
direction. Renames are handled as deletions and additions.

If the same file is edited on both sides, or deleted on one side and edited on
the other, both states are preserved and the conflict is logged. Resolve the
conflict by making both copies agree, then run the command again. Files are
compared by content, rather than choosing whichever modification time is newer.
Conflicts do not block unrelated, safe changes.

Set Finder's **Keep Downloaded** on the iCloud vault folder. Synchronization
aborts when it sees an undownloaded iCloud placeholder, an unavailable root,
or an empty replica. This prevents an unavailable folder from being interpreted
as a request to delete the other copy. Deleting every file in a replica requires
manual handling. The script cannot guarantee that Apple has uploaded changes
or received changes from other devices; it synchronizes the files currently
visible on this Mac. Avoid editing a file while it is being synchronized.

`.git`, `.DS_Store`, `.debris`, `.megaignore` and `*.icloud` are excluded. No Git
commands are run. Obsidian settings are synchronized with the other files.

## Recovery

Sync history lives at `~/.local/state/obsidian-sync/archives`. Preserve it: it
distinguishes deletions from additions. If initialized history is missing,
the command aborts. Do not delete the state folder to resolve conflicts.

Before replacing or deleting files, Unison keeps up to ten backup versions
per file under `~/.local/state/obsidian-sync/backups`. These backups are local
and do not replace a separate backup of the vault. Copy a recovered version
to both replicas to resolve a conflict deliberately.

The operating system releases the sync lock when its last owning process
exits, including when a process is killed. Unison may retain its own archive
lock after an interrupted run; if it reports that problem, confirm no engine
is running before following its lock-recovery instructions.

Exit codes: `0` success or an overlapping invocation skipped; `1` conflicts
or skipped updates; `2` failed safety check or synchronization error; `3`
partial synchronization with transfer failures. Full-vault checksum scans
can take longer than the old timestamp-based copies.

## Development

```sh
uv sync
uv run python -m unittest discover -s tests -v
```

Tests use temporary vaults and the private installed Unison binary. Set
`UNISON_BINARY` to `vendor/unison` to test before installation. CLI options
`--local`, `--icloud`, `--state-dir`, `--log-file`, and `--unison` allow separate
test configurations. Use a separate state directory for each pair of roots.
