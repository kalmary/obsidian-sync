#!/bin/bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
python_bin="${OBSIDIAN_SYNC_PYTHON:-/opt/homebrew/bin/python3}"
uv_bin="${OBSIDIAN_SYNC_UV:-$HOME/.local/bin/uv}"

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    printf '%s\n' 'This distribution requires macOS on Apple Silicon.' >&2
    exit 1
fi

"$python_bin" "$project_dir/install.py" "$project_dir" "$uv_bin" "$python_bin"
