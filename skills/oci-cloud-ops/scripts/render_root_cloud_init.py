#!/usr/bin/env python3
"""Render root-password cloud-init without persisting the plaintext password."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import shutil
import subprocess
import sys


TEMPLATE = """#cloud-config
disable_root: false
ssh_pwauth: true

chpasswd:
  expire: false
  users:
    - name: root
      password: '{password_hash}'
      type: hash

write_files:
  - path: /etc/ssh/sshd_config.d/00-oci-root-password-login.conf
    owner: root:root
    permissions: '0600'
    content: |
      PermitRootLogin yes
      PasswordAuthentication yes
      KbdInteractiveAuthentication yes
      UsePAM yes

runcmd:
  - [sh, -c, "sshd -t && (systemctl restart ssh || systemctl restart sshd)"]
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prompt twice for a root password, hash it with OpenSSL SHA-512 crypt, "
            "and render cloud-init. The plaintext is never written to disk."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Write the cloud-config with mode 0600.",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=14,
        help="Minimum password length (default: 14).",
    )
    return parser.parse_args()


def read_password(min_length: int) -> str:
    if min_length < 12:
        raise ValueError("--min-length cannot be lower than 12")
    first = getpass.getpass("New temporary root password: ")
    second = getpass.getpass("Repeat temporary root password: ")
    if first != second:
        raise ValueError("passwords do not match")
    if len(first) < min_length:
        raise ValueError(f"password must contain at least {min_length} characters")
    if any(ch in first for ch in "\r\n\x00"):
        raise ValueError("password contains a forbidden control character")
    return first


def hash_password(password: str) -> str:
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("openssl is required to generate a SHA-512 password hash")
    completed = subprocess.run(
        [openssl, "passwd", "-6", "-stdin"],
        input=(password + "\n").encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"openssl passwd failed: {detail[:200]}")
    password_hash = completed.stdout.decode().strip()
    if not password_hash.startswith("$6$"):
        raise RuntimeError("openssl returned an unexpected password hash format")
    return password_hash


def write_private(path: Path, content: str) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def main() -> int:
    args = parse_args()
    try:
        password = read_password(args.min_length)
        password_hash = hash_password(password)
        password = ""  # Best-effort removal of the plaintext reference.
        cloud_config = TEMPLATE.format(password_hash=password_hash)
        password_hash = ""
        write_private(args.output, cloud_config)
        print(f"cloud-init written with mode 0600: {args.output.expanduser().resolve()}")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
