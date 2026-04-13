#!/usr/bin/env python3
"""
Build a SubBoost-compatible local rule repository.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
SOURCES = ROOT / "sources"
GEO_GEOSITE = ROOT / "geo" / "geosite"
GEO_GEOIP = ROOT / "geo" / "geoip"
META_BASE = "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo"
TESLA_AI = "https://raw.githubusercontent.com/teslaproduuction/ClashDomainsList/main/ai.txt"
JIMMY_AI = "https://raw.githubusercontent.com/jimmyzhou521-stack/ai-projects-proxy-rules/main/rules/clash.yaml"
BASE_MRS = {
    GEO_GEOSITE / "category-ads-all.mrs": f"{META_BASE}/geosite/category-ads-all.mrs",
    GEO_GEOSITE / "private.mrs": f"{META_BASE}/geosite/private.mrs",
    GEO_GEOSITE / "geolocation-cn.mrs": f"{META_BASE}/geosite/geolocation-cn.mrs",
    GEO_GEOSITE / "geolocation-!cn.mrs": f"{META_BASE}/geosite/geolocation-!cn.mrs",
    GEO_GEOSITE / "cn.mrs": f"{META_BASE}/geosite/cn.mrs",
    GEO_GEOIP / "private.mrs": f"{META_BASE}/geoip/private.mrs",
    GEO_GEOIP / "cn.mrs": f"{META_BASE}/geoip/cn.mrs",
}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp:
        dest.write_bytes(resp.read())


def normalize_rule(line: str) -> str | None:
    line = line.strip().strip("'").strip('"')
    if not line or line.startswith("#"):
        return None
    if line.startswith("+."):
        return f"domain:{line[2:].lower()}"
    if line.startswith("DOMAIN-SUFFIX,"):
        return f"domain:{line.split(',', 1)[1].strip().lower()}"
    if line.startswith("DOMAIN,"):
        return f"full:{line.split(',', 1)[1].strip().lower()}"
    if line.startswith("DOMAIN-KEYWORD,"):
        return None
    if line.startswith("DOMAIN-REGEX,"):
        return None
    if line.startswith(("full:", "domain:")):
        head, tail = line.split(":", 1)
        return f"{head.lower()}:{tail.strip().lower()}"
    if line.startswith(("keyword:", "regexp:")):
        return None
    if re.match(r"^[A-Za-z0-9*+_.:-]+$", line):
        return f"full:{line.lower()}"
    return None


def parse_payload_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            out.append(line.split("- ", 1)[1].strip())
    return out


def parse_tesla_sections(text: str) -> dict[str, list[str]]:
    current = None
    buckets: dict[str, list[str]] = {
        "anthropic": [],
        "openai": [],
        "category-ai-chat-!cn": [],
    }
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# Anthropic"):
            current = "anthropic"
            continue
        if line.startswith("# OpenAI"):
            current = "openai"
            continue
        if line.startswith("# ") and current is not None:
            current = None
        if line.startswith("- "):
            item = line.split("- ", 1)[1].strip()
            buckets["category-ai-chat-!cn"].append(item)
            if current == "anthropic":
                buckets["anthropic"].append(item)
            elif current == "openai":
                buckets["openai"].append(item)
    return buckets


def merge_rules() -> dict[str, list[str]]:
    tesla_raw = (SOURCES / "ai.txt").read_text()
    jimmy_raw = (SOURCES / "clash.yaml").read_text()

    tesla = parse_tesla_sections(tesla_raw)
    jimmy_items = parse_payload_lines(jimmy_raw)

    merged = {
        "anthropic": set(),
        "openai": set(),
        "category-ai-chat-!cn": set(),
    }

    for name, rules in tesla.items():
        for rule in rules:
            normalized = normalize_rule(rule)
            if normalized:
                merged[name].add(normalized)

    for rule in jimmy_items:
        normalized = normalize_rule(rule)
        if not normalized:
            continue
        lower = normalized.split(":", 1)[1].lower()
        merged["category-ai-chat-!cn"].add(normalized)
        if any(key in lower for key in (
            "openai",
            "chatgpt",
            "oaistatic",
            "oaiusercontent",
            "arkoselabs",
            "browser-intake-datadoghq.com",
            "ingest.sentry.io",
            "livekit",
        )):
            merged["openai"].add(normalized)
        if any(key in lower for key in ("anthropic", "claude", "usefathom")):
            merged["anthropic"].add(normalized)

    merged["openai"].add("full:browser-intake-datadoghq.com")
    merged["openai"].add("full:o33249.ingest.sentry.io")
    merged["anthropic"].add("full:cdn.usefathom.com")

    return {name: sorted(values) for name, values in merged.items()}


def write_source_snapshots() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    download(TESLA_AI, SOURCES / "ai.txt")
    download(JIMMY_AI, SOURCES / "clash.yaml")
    (SOURCES / "upstreams.json").write_text(
        json.dumps(
            {
                "teslaproduuction_ai": TESLA_AI,
                "jimmyzhou_ai": JIMMY_AI,
                "meta_base": META_BASE,
            },
            indent=2,
        )
        + "\n"
    )


def encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            return bytes(out)


def encode_key(field_number: int, wire_type: int) -> bytes:
    return encode_varint((field_number << 3) | wire_type)


def encode_string(field_number: int, value: str) -> bytes:
    raw = value.encode()
    return encode_key(field_number, 2) + encode_varint(len(raw)) + raw


def encode_message(field_number: int, payload: bytes) -> bytes:
    return encode_key(field_number, 2) + encode_varint(len(payload)) + payload


def encode_enum(field_number: int, value: int) -> bytes:
    return encode_key(field_number, 0) + encode_varint(value)


def encode_domain(rule: str) -> bytes:
    kind, value = rule.split(":", 1)
    domain_type = {
        "domain": 2,
        "full": 3,
    }[kind]
    return encode_enum(1, domain_type) + encode_string(2, value)


def encode_geosite(name: str, rules: list[str]) -> bytes:
    payload = bytearray()
    payload.extend(encode_string(1, name))
    for rule in rules:
        payload.extend(encode_message(2, encode_domain(rule)))
    return bytes(payload)


def make_geosite_dat(data_map: dict[str, list[str]]) -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    payload = bytearray()
    for name, rules in sorted(data_map.items()):
        payload.extend(encode_message(1, encode_geosite(name, rules)))
    out = BUILD / "geosite.dat"
    out.write_bytes(bytes(payload))
    return out


def mirror_base_rules() -> None:
    for dest, url in BASE_MRS.items():
        download(url, dest)


def clean_previous_ai_outputs() -> None:
    for name in ("openai", "anthropic", "category-ai-chat-!cn"):
        for suffix in (".mrs", ".yaml", ".list"):
            target = GEO_GEOSITE / f"{name}{suffix}"
            if target.exists():
                target.unlink()
        txt_target = BUILD / f"{name}.txt"
        if txt_target.exists():
            txt_target.unlink()
    classical = GEO_GEOSITE / "classical"
    if classical.exists():
        for name in ("openai", "anthropic", "category-ai-chat-!cn"):
            for suffix in (".yaml", ".list"):
                target = classical / f"{name}{suffix}"
                if target.exists():
                    target.unlink()


def reverse_text(value: str) -> str:
    return value[::-1]


def set_bit(words: list[int], bit_index: int, value: int) -> None:
    while bit_index >> 6 >= len(words):
        words.append(0)
    if value:
        words[bit_index >> 6] |= 1 << (bit_index & 63)


def build_domain_set(rules: list[str]) -> tuple[list[int], list[int], bytes]:
    keys = []
    for rule in rules:
        kind, value = rule.split(":", 1)
        if kind == "full":
            keys.append(reverse_text(value))
        elif kind == "domain":
            keys.append(reverse_text(value))
    keys = sorted(set(keys))
    if not keys:
        raise ValueError("empty domain rules")

    leaves: list[int] = []
    label_bitmap: list[int] = []
    labels = bytearray()
    queue: list[tuple[int, int, int]] = [(0, len(keys), 0)]
    label_index = 0
    idx = 0

    while idx < len(queue):
        start, end, col = queue[idx]
        if col == len(keys[start]):
            start += 1
            set_bit(leaves, idx, 1)

        j = start
        while j < end:
            frm = j
            while j < end and keys[j][col] == keys[frm][col]:
                j += 1
            queue.append((frm, j, col + 1))
            labels.extend(keys[frm][col].encode())
            set_bit(label_bitmap, label_index, 0)
            label_index += 1

        set_bit(label_bitmap, label_index, 1)
        label_index += 1
        idx += 1

    return leaves, label_bitmap, bytes(labels)


def encode_domain_set_bin(rules: list[str]) -> bytes:
    leaves, label_bitmap, labels = build_domain_set(rules)
    out = bytearray()
    out.extend(b"\x01")
    out.extend(struct.pack(">q", len(leaves)))
    for word in leaves:
        out.extend(struct.pack(">Q", word))
    out.extend(struct.pack(">q", len(label_bitmap)))
    for word in label_bitmap:
        out.extend(struct.pack(">Q", word))
    out.extend(struct.pack(">q", len(labels)))
    out.extend(labels)
    return bytes(out)


def write_mrs_domain(rules: list[str], dest: Path) -> None:
    zstd = shutil.which("zstd") or "/opt/homebrew/bin/zstd"
    if not Path(zstd).exists():
        raise FileNotFoundError("zstd binary not found in PATH")

    raw = bytearray()
    raw.extend(b"MRS\x01")
    raw.extend(b"\x00")
    raw.extend(struct.pack(">q", len(rules)))
    raw.extend(struct.pack(">q", 0))
    raw.extend(encode_domain_set_bin(rules))

    tmp = dest.with_suffix(dest.suffix + ".raw")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(bytes(raw))
    subprocess.run([zstd, "-q", "-f", str(tmp), "-o", str(dest)], check=True)
    tmp.unlink(missing_ok=True)


def main() -> int:
    mirror_base_rules()
    write_source_snapshots()
    clean_previous_ai_outputs()
    data_map = merge_rules()
    geosite_dat = make_geosite_dat(data_map)
    for name, rules in data_map.items():
        (BUILD / f"{name}.txt").write_text("\n".join(rules) + "\n")
        write_mrs_domain(rules, GEO_GEOSITE / f"{name}.mrs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
