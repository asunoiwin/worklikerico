# Shadowsocks-libev server

Use this path only for an explicitly requested server node. It is separate from the interactive forwarding installers.

## Safe service shape

- Use a dedicated unprivileged account and a dedicated custom unit such as `shadowsocks-rno-NAME.service`.
- Keep the server config owned by `root:SERVICE_GROUP` with mode `0640`.
- Do not use a package template instance when the logical name contains `-`. systemd interprets `%I` as a path-escaped instance and a name such as `japan-chain` can resolve to an unintended config path.
- Do not work around config-read failures with a world-readable secret or by running the service as root. Use the dedicated account/group and explicit `User=`/`Group=` settings.
- Keep the password out of argv, shell history, logs, and command output. Write it through an approved secret-aware channel and never echo the completed config.

The unit must call `ss-server` with an absolute config path, set `User=` and `Group=`, restart on failure, and use ordinary systemd hardening compatible with UDP and TCP sockets. Disable any failed template instance created during an abandoned attempt and clear only that unit's failed state.

## Verification

1. Validate the JSON without printing it.
2. Start and enable the custom unit.
3. Run `scripts/wait_for_listener.sh SERVICE PORT 30 tcp` and again with `udp`.
4. Confirm the configured cipher, TCP/UDP mode, restart persistence, and error-free recent journal.
5. If the user will test the client, stop there. Return the requested URI only when explicitly requested, and do not install a client on a forwarding host.
