#!/usr/bin/env bash
set -u

install_dir="${HOME}/.local/share/worklikerico/hermes-agent"
expected_commit="2237be355906fbe6065ce1815711eee52b2d646e"

if [[ ! -d "${install_dir}/.git" ]]; then
  printf 'Hermes installation missing: %s\n' "${install_dir}"
  exit 0
fi

actual_commit="$(git -C "${install_dir}" rev-parse HEAD 2>/dev/null || true)"
if [[ "${actual_commit}" != "${expected_commit}" ]]; then
  printf 'Hermes version drift: expected %s, found %s\n' "${expected_commit}" "${actual_commit:-unknown}"
  exit 0
fi

if [[ -n "$(git -C "${install_dir}" status --porcelain 2>/dev/null)" ]]; then
  printf 'Hermes upstream checkout has local changes: %s\n' "${install_dir}"
fi
