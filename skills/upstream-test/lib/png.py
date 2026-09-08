"""用 sips 生成 200x200 真实 PNG。"""
import base64
import os
import subprocess
import tempfile

_CACHE = {}


def mk_real_png() -> tuple:
    """返回 (path, base64_str)。优先用系统现成 Solid Colors，否则 fallback 用 PIL/纯字节。"""
    if "data" in _CACHE:
        return _CACHE["path"], _CACHE["data"]

    candidates = [
        "/System/Library/Desktop Pictures/Solid Colors/Red Orange.png",
        "/System/Library/Desktop Pictures/Solid Colors/Red.png",
        "/Library/Desktop Pictures/Solid Colors/Red.png",
    ]
    src = next((p for p in candidates if os.path.exists(p)), None)
    out = os.path.join(tempfile.gettempdir(), "upstream_test_red200.png")

    if src:
        try:
            subprocess.run(
                ["/usr/bin/sips", "-s", "format", "png", src,
                 "--resampleWidth", "200", "--out", out],
                check=True, capture_output=True, timeout=15,
            )
        except Exception:
            src = None

    if not src or not os.path.exists(out):
        # fallback: 写一个最小但合法的红色 PNG（手动构造 200x200 红色，使用 zlib 压缩）
        import struct, zlib
        w = h = 200
        raw = b""
        for _ in range(h):
            raw += b"\x00" + (b"\xff\x00\x00") * w  # filter byte + RGB red
        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        idat = zlib.compress(raw, 9)
        png = sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
        with open(out, "wb") as f:
            f.write(png)

    with open(out, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    _CACHE["path"] = out
    _CACHE["data"] = b64
    return out, b64
