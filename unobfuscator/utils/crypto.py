from __future__ import annotations
from typing import List, Optional, Tuple
import struct
import hashlib
import base64


def xor_decrypt(data: bytes, key: bytes) -> bytes:
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def xor_decrypt_str(data: str, key: int) -> str:
    return ''.join(chr(ord(c) ^ (key & 0xFF)) for c in data)


def xor_decrypt_rolling(data: bytes, key: int) -> bytes:
    result = bytearray(len(data))
    k = key & 0xFFFFFFFF
    for i, b in enumerate(data):
        result[i] = b ^ (k & 0xFF)
        k = ((k * 1103515245 + 12345) & 0xFFFFFFFF)
    return bytes(result)


def caesar_decrypt(data: str, shift: int) -> str:
    result = []
    for c in data:
        if 'a' <= c <= 'z':
            result.append(chr((ord(c) - ord('a') - shift) % 26 + ord('a')))
        elif 'A' <= c <= 'Z':
            result.append(chr((ord(c) - ord('A') - shift) % 26 + ord('A')))
        else:
            result.append(c)
    return ''.join(result)


BASE91_TABLE = (
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    '0123456789!#$%&()*+,./:;<=>?@[]^_`{|}~"'
)

def base91_decode(data: str) -> bytes:
    lookup = {c: i for i, c in enumerate(BASE91_TABLE)}
    result = bytearray()
    v = -1
    b = 0
    n = 0
    for c in data:
        if c not in lookup:
            continue
        ci = lookup[c]
        if v < 0:
            v = ci
        else:
            v += ci * 91
            b |= (v << n)
            n += 13 if (v & 0x1FFF) > 88 else 14
            while n >= 8:
                result.append(b & 0xFF)
                b >>= 8
                n -= 8
            v = -1
    if v >= 0:
        result.append((b | (v << n)) & 0xFF)
    return bytes(result)


def base91_encode(data: bytes) -> str:
    result = []
    b = 0
    n = 0
    for byte in data:
        b |= byte << n
        n += 8
        if n > 13:
            v = b & 0x1FFF
            if v > 88:
                b >>= 13
                n -= 13
            else:
                v = b & 0x3FFF
                b >>= 14
                n -= 14
            result.append(BASE91_TABLE[v % 91])
            result.append(BASE91_TABLE[v // 91])
    if n:
        result.append(BASE91_TABLE[b % 91])
        if n > 7 or b > 90:
            result.append(BASE91_TABLE[b // 91])
    return ''.join(result)


def lzss_decompress(data: bytes) -> bytes:
    if len(data) < 4:
        return data
    result = bytearray()
    pos = 0
    try:
        orig_size = struct.unpack('<I', data[:4])[0]
        pos = 4
        while pos < len(data) and len(result) < orig_size:
            flags = data[pos]
            pos += 1
            for bit in range(8):
                if pos >= len(data) or len(result) >= orig_size:
                    break
                if flags & (1 << bit):
                    result.append(data[pos])
                    pos += 1
                else:
                    if pos + 1 >= len(data):
                        break
                    b1 = data[pos]
                    b2 = data[pos + 1]
                    pos += 2
                    offset = ((b2 & 0xF0) << 4) | b1
                    length = (b2 & 0x0F) + 3
                    for _ in range(length):
                        if offset < len(result):
                            result.append(result[-offset - 1])
                        else:
                            result.append(0)
    except (struct.error, IndexError):
        pass
    return bytes(result)


def rc4_decrypt(data: bytes, key: bytes) -> bytes:
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    i = j = 0
    result = bytearray(len(data))
    for k in range(len(data)):
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        result[k] = data[k] ^ S[(S[i] + S[j]) % 256]
    return bytes(result)


def simple_hash(data: str) -> int:
    h = 0
    for c in data:
        h = ((h << 5) - h + ord(c)) & 0xFFFFFFFF
    return h


def detect_encoding(data: str) -> Optional[str]:
    try:
        base64.b64decode(data, validate=True)
        return 'base64'
    except Exception:
        pass
    if all(c in BASE91_TABLE or c.isspace() for c in data):
        decoded = base91_decode(data)
        if decoded and len(decoded) < len(data):
            return 'base91'
    try:
        bytes.fromhex(data.replace(' ', ''))
        return 'hex'
    except ValueError:
        pass
    return None


def try_decode(data: str) -> Optional[bytes]:
    encoding = detect_encoding(data)
    if encoding == 'base64':
        return base64.b64decode(data)
    if encoding == 'base91':
        return base91_decode(data)
    if encoding == 'hex':
        return bytes.fromhex(data.replace(' ', ''))
    return None


def brute_xor_key(ciphertext: bytes, known_plaintext: bytes, offset: int = 0) -> Optional[bytes]:
    if not ciphertext or not known_plaintext:
        return None
    key_bytes = []
    for i, (c, p) in enumerate(zip(ciphertext[offset:], known_plaintext)):
        key_bytes.append(c ^ p)
    if not key_bytes:
        return None
    for key_len in range(1, min(len(key_bytes) + 1, 33)):
        key = bytes(key_bytes[:key_len])
        valid = True
        for i in range(len(key_bytes)):
            if key_bytes[i] != key[i % key_len]:
                valid = False
                break
        if valid:
            return key
    return bytes(key_bytes)


def string_char_decode(char_values: List[int]) -> str:
    return ''.join(chr(v & 0xFF) for v in char_values)


def reverse_string(s: str) -> str:
    return s[::-1]


def rot13(s: str) -> str:
    return caesar_decrypt(s, 13)


def byte_sub_decrypt(data: bytes, sub_table: List[int]) -> bytes:
    if len(sub_table) != 256:
        return data
    inv = [0] * 256
    for i, v in enumerate(sub_table):
        inv[v & 0xFF] = i
    return bytes(inv[b] for b in data)
