# Script catalog

| Role | Default source | China bootstrap source | Typical target |
|---|---|---|---|
| BBR | `https://github.000060000.xyz/tcp.sh` | jsDelivr copy of `ylx2016/Linux-NetSpeed/tcp.sh` | Ubuntu/Debian and CentOS/RHEL families; choose the script menu appropriate to the detected kernel |
| V2Ray | `https://git.io/v2ray.sh` | jsDelivr copy of `233boy/v2ray/install.sh` | Ubuntu/Debian and CentOS/RHEL families |
| GOST | `raw.githubusercontent.com/KANIKIG/.../gost.sh` | jsDelivr copy of the same file; do not select its broken OSS mirror | Ubuntu/Debian and CentOS/RHEL families |
| iptables | `file.goalnowtech.com/iptables-pf.sh`; reviewed GitHub fallback | jsDelivr copy of `ToyoDAdoubiBackup/doubi/iptables-pf.sh` | Linux with iptables compatibility; inspect nftables coexistence first |
| Brook | `raw.githubusercontent.com/monret/.../brook-pf-mod.sh` | jsDelivr copy of the same file | Ubuntu/Debian and CentOS/RHEL families |
| Shadowsocks-libev server | Distribution package; no third-party installer | Not applicable | Use the isolated custom-unit workflow in `shadowsocks-libev.md` |

Use `--china-source` for the listed mainland route. Override a direct source with `--url URL`, or use a controller-downloaded file with `--local-script FILE`. `--url` and `--china-source` are intentionally mutually exclusive.

These URLs are mutable. The cache hash and inspection are required for traceability; they are not claims that upstream content is permanently safe.
