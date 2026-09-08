# Mainland source validation

Validated on 2026-08-19. The Korean Linux host was used only for Linux execution mechanics; mainland reachability was measured separately with ITDOG Telecom, Unicom, and Mobile nodes.

## Reachability result

The same GOST raw script path was used to compare the generic bootstrap routes:

| Route | Successful mainland nodes | Result |
|---|---:|---|
| `cdn.jsdelivr.net/gh/...` | 230/238 (96.6%) | primary bootstrap |
| `ghproxy.net/https://raw...` | 233/239 (97.5%) | bootstrap fallback |
| `gh-proxy.com/https://raw...` | 231/239 (96.7%) | internal GitHub adapter |
| `ghfast.top/https://raw...` | 154/239 (64.4%) | rejected; especially poor on Mobile |
| GOST built-in Aliyun OSS | 0/239 | rejected; endpoint unavailable |
| `gh-proxy.com` Brook release asset | 235/239 (98.3%) | internal release download verified |
| `gh-proxy.com` GitHub API path | 235/239 (98.3%) | GOST version lookup verified |

Public proxy availability can change. If these routes fail, use the controller-download plus SCP fallback instead of adding more unreviewed mirrors.

## Content equality

Controller downloads from GitHub origin, jsDelivr, and the raw proxy had identical SHA-256 values for the five bootstrap scripts:

| Role | SHA-256 |
|---|---|
| BBR | `0b7614e7f5b0de93d7bfd790be672c26c54b223b47ec1b1ae5fa2884e2ea61c0` |
| V2Ray | `64e01e5ff54e611f1ab61a80feb2479fd305fde5dc9a557162ca6aa43119af3c` |
| GOST | `c5a61e244d394dac7388d292986f3815741cc69a8d294d3ee50e0dc6472ed560` |
| iptables | `4a6ccfbccb0c2d650b309ebd897e68048dbb428d206a742c26eaa978e6fcdfa2` |
| Brook | `10f11ad9e0d083410f871c9823fb43d650d4923ba622ac01d26f94041c5d2fb8` |

These hashes are observations, not permanent pins. The upstream branches are mutable; compare and review again when the hash changes.

## Internal downloads

V2Ray, GOST, Brook, and iptables installers make later GitHub release, raw, or API requests. China mode rewrites those URLs in the cached copy to `gh-proxy.com`. Its raw-file, Brook release, and GOST GitHub API routes were measured from mainland nodes. All are covered by the controller-download plus SCP fallback if a target still cannot reach them. BBR is not rewritten because its own script already detects China and selects a proxy for its kernel downloads.

The supplied Brook manager is legacy code. Its automatic latest release is incompatible with the removed `relays` command, so the prepared copy defaults to `v20200801`, the last release whose `brook` asset was verified to expose `relays` on Linux. This preserves the supplied manager's behavior but is explicitly an old-version tradeoff.
