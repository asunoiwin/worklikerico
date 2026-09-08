# Existing installer review notes

The scripts are usable, but they are powerful interactive installers. Review the cached file before each changed SHA-256.

- `tcp.sh`: may replace/remove kernels, edit GRUB, download more content, and reboot. Only run the selected acceleration action after a maintenance-window confirmation.
- `v2ray.sh`: follows a short link and downloads additional files. Record the resolved URL and cached hash.
- `gost.sh`: may remove existing GOST files/services and use more than one download source. Back up current GOST configuration first.
- `iptables-pf.sh`: the supplied host was unreachable during the initial audit. The fallback is the archived `ToyoDAdoubiBackup/doubi` copy; it is old and may replace firewall services, so inspect current nftables/firewalld state first.
- `brook-pf-mod.sh`: may modify firewall policy and persistence. Its automatic latest-version path is incompatible because current Brook no longer has the `relays` command. The adapter therefore defaults to the last verified compatible release, `v20200801`; this is an old binary and must be treated as a deliberate legacy choice. Save `iptables-save`/`nft list ruleset` first and check that SSH remains reachable.

The Skill may execute these after inspection and explicit confirmation. It must not silently pipe a fresh network response directly to Bash.
