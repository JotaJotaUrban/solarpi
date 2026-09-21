#!/usr/bin/env bash
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec bash "$script_dir/apply_update.sh" "$@"
