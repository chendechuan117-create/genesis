#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import math
import sys
from pathlib import Path

COMMON = {
    " ": 8.0,
    "e": 5.0,
    "t": 4.5,
    "a": 4.0,
    "o": 3.8,
    "i": 3.6,
    "n": 3.5,
    "s": 3.4,
    "r": 3.3,
    "h": 3.0,
    "l": 2.4,
    "d": 2.2,
    "c": 2.0,
    "u": 1.8,
    "m": 1.7,
    "f": 1.6,
    "p": 1.5,
    "g": 1.4,
    "y": 1.3,
    "b": 1.2,
    "\n": 1.0,
    "_": 0.8,
    "=": 0.7,
    "(": 0.5,
    ")": 0.5,
    ":": 0.5,
    ".": 0.5,
    ",": 0.4,
    "'": 0.4,
    '"': 0.4,
}


def xor_repeat(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def hamming(a: bytes, b: bytes) -> int:
    return sum((x ^ y).bit_count() for x, y in zip(a, b))


def score_plain(buf: bytes) -> float:
    score = 0.0
    for b in buf:
        c = chr(b)
        lc = c.lower()
        if lc in COMMON:
            score += COMMON[lc]
        elif 32 <= b <= 126:
            score += 0.15
        elif b in (9, 10, 13):
            score += 0.2
        else:
            score -= 12.0
    try:
        text = buf.decode("utf-8")
    except UnicodeDecodeError:
        score -= len(buf) * 5.0
        text = ""
    if text:
        for marker in ("def ", "return ", "for ", "if ", "score", "candidate", "metrics", "status"):
            score += text.count(marker) * 6.0
    return score / max(len(buf), 1)


def normalized_distance(cipher: bytes, keysize: int) -> float:
    blocks = [cipher[i : i + keysize] for i in range(0, min(len(cipher), keysize * 10), keysize)]
    blocks = [b for b in blocks if len(b) == keysize]
    if len(blocks) < 2:
        return math.inf
    pairs = []
    for i in range(len(blocks) - 1):
        pairs.append(hamming(blocks[i], blocks[i + 1]) / keysize)
    return sum(pairs) / len(pairs)


def best_single_byte(column: bytes) -> int:
    return max(range(256), key=lambda k: score_plain(bytes(b ^ k for b in column)))


def solve(cipher: bytes) -> tuple[bytes, bytes]:
    candidates = []
    keysize_order = sorted(range(2, 41), key=lambda k: normalized_distance(cipher, k))
    for keysize in keysize_order[:18]:
        key = bytes(best_single_byte(cipher[i::keysize]) for i in range(keysize))
        plaintext = xor_repeat(cipher, key)
        candidates.append((score_plain(plaintext), key, plaintext))
    _, key, plaintext = max(candidates, key=lambda item: item[0])
    return key, plaintext


def main() -> None:
    challenge_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
    answers = []
    for case in challenge["hidden_cases"]:
        cipher = base64.b64decode(case["ciphertext_b64"])
        key, plaintext = solve(cipher)
        answers.append(
            {
                "id": case["id"],
                "key": key.decode("latin1"),
                "plaintext": plaintext.decode("utf-8", errors="replace"),
            }
        )
    output_path.write_text(json.dumps({"answers": answers}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
