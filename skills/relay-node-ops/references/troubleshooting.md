# Troubleshooting record

## 2026-08-24: nested SSH shell quoting failed

- Symptom: an inventory command expanded remote shell variables in the wrong shell and exited before inspection completed.
- Root cause: a multiline script was embedded inside nested local and remote quote layers.
- Fix: send non-trivial remote scripts with `ssh host 'bash -s' <<'REMOTE'` or a reviewed encoded payload. Do not interpolate secrets.

## 2026-08-24: Shadowsocks systemd template resolved the wrong config

- Symptom: a template instance named with a hyphen looked for a path-separated config name; a second template attempt could not read the root-only config under `DynamicUser=`.
- Root cause: reliance on `%I` path escaping and a service identity that did not match the secret-file permissions.
- Fix: use a custom unit with an absolute config path, a dedicated service account, and `root:service-group` mode `0640`. See [shadowsocks-libev.md](shadowsocks-libev.md).

## 2026-08-24: immediate listener assertion raced service startup

- Symptom: `systemctl enable --now` succeeded but an immediate `ss` assertion failed; the listener appeared moments later.
- Root cause: service activation and socket readiness are separate states.
- Fix: use the bounded `scripts/wait_for_listener.sh` check.

## 2026-08-24: client acceptance boundary was crossed

- Symptom: a temporary client package installation began on a forwarding host even though the user intended to test the client themselves.
- Root cause: the workflow treated end-to-end client validation as unconditional.
- Fix: when the user reserves acceptance testing, verify only server, listener, persistence, and authorized hops; leave no client packages, processes, or temporary configs.

## 2026-08-24: local validation harness assumptions failed

- Symptom: `quick_validate.py` failed under Python environments without PyYAML, and a zsh wrapper attempted to assign the reserved variable `status`.
- Root cause: the validation command assumed an undeclared Python dependency and a bash-compatible variable name.
- Fix: run the validator with an existing environment that provides PyYAML and use a neutral result variable such as `test_rc`. These failures occurred only in the local test harness; the skill tests still need to be rerun and pass before release.
