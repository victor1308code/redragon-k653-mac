#!/usr/bin/env python3
"""
Extract Redragon K653-RGB-PRO assets and reverse-engineered HID protocol metadata
from the official Windows Inno Setup 5.3.3 installer using Python LZMA + CallInstructionOptimize
unfilter and REA / objdump inspection.
"""

from __future__ import annotations

import hashlib
import json
import lzma
import os
import re
import struct
from pathlib import Path
from typing import Any

EXE_PATH = Path(
    os.environ.get(
        "K653_SETUP_EXE",
        str(
            Path.home()
            / "Downloads"
            / "Redragon K653-RGB-PRO (wired and 3mode) V1.6.6 20230505"
            / "Redragon K653-RGB-PRO Setup V1.6.6 20230505.exe"
        ),
    )
)
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
DUMP_PATH = ASSETS_DIR / "k653_rea_dump.json"


def _read_inno_block(data: bytes, offset: int) -> tuple[bytes, int]:
    _, stored_size, compressed = struct.unpack_from("<IIB", data, offset)
    offset += 9
    raw = data[offset : offset + stored_size]
    offset += stored_size

    chunks = bytearray()
    cpos = 0
    while cpos < len(raw):
        chunk = raw[cpos + 4 : cpos + 4 + 4096]
        chunks.extend(chunk)
        cpos += 4 + len(chunk)

    if not compressed:
        return bytes(chunks), offset

    props = bytes(chunks[:5])
    lc = props[0] % 9
    rem = props[0] // 9
    lp = rem % 5
    pb = rem // 5
    dict_size = struct.unpack_from("<I", props, 1)[0]
    dec = lzma.LZMADecompressor(
        format=lzma.FORMAT_RAW,
        filters=[{"id": lzma.FILTER_LZMA1, "lc": lc, "lp": lp, "pb": pb, "dict_size": dict_size}],
    )
    return dec.decompress(bytes(chunks[5:])), offset


def _unfilter_inno_533_calls(data: bytes, block_size: int = 65536) -> bytes:
    """Undo Inno Setup 5.3.3 CallInstructionOptimize transform (0xE8/0xE9 in 64KB blocks)."""
    buf = bytearray(data)
    n = len(buf)
    for start in range(0, n, block_size):
        end = min(n, start + block_size)
        i = start
        while i <= end - 5:
            if buf[i] in (0xE8, 0xE9):
                b4 = buf[i + 4]
                if b4 in (0x00, 0xFF):
                    addr = i + 5
                    v24 = buf[i + 1] | (buf[i + 2] << 8) | (buf[i + 3] << 16)
                    r24 = (v24 - addr) & 0xFFFFFF
                    buf[i + 1] = r24 & 0xFF
                    buf[i + 2] = (r24 >> 8) & 0xFF
                    buf[i + 3] = (r24 >> 16) & 0xFF
                i += 5
            else:
                i += 1
    return bytes(buf)


def parse_cfg_ini(text: str) -> dict[str, Any]:
    vid = 0x258A
    pid = 0x0049
    title = "Redragon K653-RGB-PRO"
    psd: list[int] = [2, 0, 0, 0, 1, 35]
    led_opts: list[dict[str, int]] = []
    keys: list[dict[str, Any]] = []

    lines = text.splitlines()
    last_comment = ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(";"):
            last_comment = line.lstrip(";").strip()
            continue
        if line.startswith("//") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        k, v = [p.strip() for p in line.split("=", 1)]
        if k == "VID":
            vid = int(v, 0)
        elif k == "PID":
            pid = int(v, 0)
        elif k == "Title":
            title = v
        elif k == "PSD":
            psd = [int(x.strip(), 0) for x in v.split(",") if x.strip()]
        elif k.startswith("LedOpt"):
            nums = [int(x.strip(), 0) for x in v.split(",") if x.strip()]
            if len(nums) >= 7:
                led_opts.append(
                    {
                        "slot": int(k[len("LedOpt"):]),
                        "ui_index": nums[0],
                        "hw_effect": nums[1],
                        "has_speed": nums[2],
                        "has_brightness": nums[3],
                        "has_direction": nums[4],
                        "has_random": nums[5],
                        "has_color": nums[6],
                    }
                )
        elif re.fullmatch(r"K\d+", k):
            parts = [x.strip() for x in v.split(",")]
            if len(parts) >= 9:
                keys.append(
                    {
                        "id": k,
                        "index": int(k[1:]),
                        "label": last_comment or k,
                        "x1": int(parts[0]),
                        "y1": int(parts[1]),
                        "x2": int(parts[2]),
                        "y2": int(parts[3]),
                        "vk_type": int(parts[4], 0),
                        "vk_code": int(parts[5], 0),
                        "matrix_idx": int(parts[7], 0),
                        "led_idx": int(parts[8], 0),
                    }
                )
            last_comment = ""

    return {
        "title": title,
        "vid": vid,
        "pid": pid,
        "vid_hex": f"0x{vid:04X}",
        "pid_hex": f"0x{pid:04X}",
        "psd": psd,
        "led_opts": led_opts,
        "keys": keys,
    }


def extract_all(exe_path: Path = EXE_PATH) -> dict[str, Any]:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    raw = exe_path.read_bytes()
    exe_sha256 = hashlib.sha256(raw).hexdigest()

    inno_off = raw.rfind(b"Inno Setup Setup Data")
    zlb_off = raw.find(b"zlb\x1a")
    if inno_off < 0 or zlb_off < 0:
        raise RuntimeError("Inno Setup 5.3.3 headers not found in installer.")

    _, pos2 = _read_inno_block(raw, inno_off + 64)
    hdr2, _ = _read_inno_block(raw, pos2)

    props = raw[zlb_off + 4 : zlb_off + 9]
    lc = props[0] % 9
    rem = props[0] // 9
    lp = rem % 5
    pb = rem // 5
    dict_size = struct.unpack_from("<I", props, 1)[0]
    dec = lzma.LZMADecompressor(
        format=lzma.FORMAT_RAW,
        filters=[{"id": lzma.FILTER_LZMA1, "lc": lc, "lp": lp, "pb": pb, "dict_size": dict_size}],
    )
    payload = dec.decompress(raw[zlb_off + 9 : inno_off])

    n_entries = len(hdr2) // 70
    extracted_files: dict[str, str] = {}
    cfg_text = ""
    xml_text = ""
    kbd_drv_md5_ok = False
    kbd_drv_sha256 = ""

    for i in range(n_entries):
        _, _, _, csub, orig, _, expected_md5, _, _, _, flags = struct.unpack_from(
            "<IIIQQQ16sQIIH", hdr2, i * 70
        )
        chunk = payload[csub : csub + orig]
        if flags & 0x10:
            chunk = _unfilter_inno_533_calls(chunk)
        md5_ok = hashlib.md5(chunk).digest() == expected_md5

        if i == 60:
            (ASSETS_DIR / "Cfg.ini").write_bytes(chunk)
            cfg_text = chunk.decode("latin1", errors="replace")
            extracted_files["Cfg.ini"] = str(ASSETS_DIR / "Cfg.ini")
        elif i == 61:
            (ASSETS_DIR / "main_nr.png").write_bytes(chunk)
            extracted_files["main_nr.png"] = str(ASSETS_DIR / "main_nr.png")
        elif i == 62:
            (ASSETS_DIR / "keyimg.png").write_bytes(chunk)
            extracted_files["keyimg.png"] = str(ASSETS_DIR / "keyimg.png")
        elif i == 64:
            (ASSETS_DIR / "text.xml").write_bytes(chunk)
            xml_text = chunk.decode("utf-16", errors="replace")
            extracted_files["text.xml"] = str(ASSETS_DIR / "text.xml")
        elif i == 57:
            (ASSETS_DIR / "appico.ico").write_bytes(chunk)
            extracted_files["appico.ico"] = str(ASSETS_DIR / "appico.ico")
        elif i == 65:
            kbd_drv_md5_ok = md5_ok
            kbd_drv_sha256 = hashlib.sha256(chunk).hexdigest()

    cfg_parsed = parse_cfg_ini(cfg_text)
    led_names: dict[int, str] = {}
    for m in re.finditer(r"<tc_led_mode(\d+)>([^<]*)</tc_led_mode\1>", xml_text):
        led_names[int(m.group(1))] = m.group(2).strip()

    dump = {
        "source_exe": str(exe_path),
        "source_sha256": exe_sha256,
        "keyboard_drv_md5_verified": kbd_drv_md5_ok,
        "keyboard_drv_sha256": kbd_drv_sha256,
        "extracted_files": extracted_files,
        "cfg": cfg_parsed,
        "led_mode_names_en": led_names,
        "hid_protocol": {
            "wired_vid": "0x258A",
            "wired_pid": "0x0049",
            "wireless_24g_vid": "0x25A7",
            "wireless_24g_pid": "0xFA70",
            "feature_report_cmd": "0x05 (6B)",
            "feature_report_data": "0x06 (1032B)",
            "feature_report_live_rgb": "0x08 (382B)",
            "commands": {
                "GetPassword": "SET_FEATURE 0x05 [05 05 81 00 00 00] -> GET_FEATURE 0x05 [05 01 <6B PSD>]",
                "GetProfile": "SET_FEATURE 0x05 [05 83 C6 00 00 00] -> GET_FEATURE 0x06 (1032B, 136B profile at [8:144])",
                "SetProfile": "SET_FEATURE 0x06 [06 03 C6 00 00 00 00 00 <136B profile> ...]",
                "SetLedRgbTab": "SET_FEATURE 0x06 [06 08 C8 00 40 00 00 00 <21 zero> <20*21B RGB table>]",
                "SetLedMatrix": "SET_FEATURE 0x06 [06 09 CC/D0 00 40 00 00 00 <1024B per-key R/G/B planes>]",
                "SetKeyMatrix": "SET_FEATURE 0x06 [06 04 D8 00 40 00 00 00 <1024B keymap>]",
                "SendMusicRGB": "SET_FEATURE 0x08 [08 0A 7A 01 <378B live R/G/B planes>]",
            },
        },
    }
    DUMP_PATH.write_text(json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8")
    return dump


if __name__ == "__main__":
    result = extract_all()
    print(
        f"Extracted Redragon K653-RGB-PRO assets -> {DUMP_PATH} "
        f"(KeyboardDrv MD5 ok={result['keyboard_drv_md5_verified']}, keys={len(result['cfg']['keys'])})"
    )
