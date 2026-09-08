#!/usr/bin/env bash
set -u

export HERMES_HOME="${HERMES_HOME:-${HOME}/.config/worklikerico/hermes}"
hermes_bin="${HERMES_BIN:-${HOME}/.local/share/worklikerico/hermes-venv/bin/hermes}"
python_bin="${HERMES_PYTHON:-${HOME}/.local/share/worklikerico/hermes-venv/bin/python}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

"${hermes_bin}" --version
"${python_bin}" -c 'import telegram; print("python-telegram-bot", telegram.__version__)'
"${hermes_bin}" config check
"${python_bin}" "${repo_root}/integrations/hermes/verify-safe-config.py" --home "${HERMES_HOME}"
"${hermes_bin}" doctor
"${hermes_bin}" cron status
"${hermes_bin}" cron list --all
"${hermes_bin}" kanban stats
