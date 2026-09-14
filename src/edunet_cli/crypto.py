"""Compatibility with ePortal RSAUtils; this is not a general RSA implementation."""

import re

from .errors import PortalError


def validate_key(exponent: str, modulus: str) -> tuple[int, int]:
    if not re.fullmatch(r"[0-9a-fA-F]{1,8}", exponent) or not re.fullmatch(
        r"[0-9a-fA-F]{128,1024}", modulus
    ):
        raise PortalError("门户 RSA 公钥格式无效。")
    n, e = int(modulus, 16), int(exponent, 16)
    if n.bit_length() < 512 or n % 2 == 0 or e < 3 or e % 2 == 0:
        raise PortalError("门户 RSA 公钥无效。")
    return n, e


def encrypt_password(password: str, mac: str, exponent: str, modulus: str) -> str:
    # 与门户 security.js 的 RSAUtils 一致：UTF-16 单元反转、零填充、小端分块。
    if not (password + mac).isascii():
        raise PortalError(
            "此版本仅支持 ASCII 密码（英文字母、数字和半角符号）；其他密码请使用网页登录。"
        )
    raw = (password + ">" + mac).encode("utf-16-le", "surrogatepass")
    units = [int.from_bytes(raw[i : i + 2], "little") for i in range(0, len(raw), 2)][::-1]
    n, e = validate_key(exponent, modulus)
    size = 2 * ((n.bit_length() - 1) // 16)
    if size < 2 or e < 3:
        raise PortalError("门户 RSA 公钥无效。")
    units += [0] * (-len(units) % size)
    blocks = []
    for start in range(0, len(units), size):
        block = sum(
            (units[j] + (units[j + 1] << 8)) << (8 * (j - start))
            for j in range(start, start + size, 2)
        )
        value = format(pow(block, e, n), "x")
        blocks.append(value.zfill((len(value) + 3) // 4 * 4))
    return " ".join(blocks)
