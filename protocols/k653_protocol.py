#!/usr/bin/env python3
"""
Byte-exact HID Feature Report protocol for the Redragon K653-RGB-PRO (VID=0x258A, PID=0x0049).
Reverse-engineered from Redragon K653-RGB-PRO Setup V1.6.6 20230505.exe -> KeyboardDrv.exe + Cfg.ini.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

K653_WIRED_VID = 0x258A
K653_WIRED_PID = 0x0049
K653_24G_VID = 0x25A7
K653_24G_PID = 0xFA70

K653_PSD = bytes([0x02, 0x00, 0x00, 0x00, 0x01, 0x23])  # PSD=2,0,0,0,1,35 from Cfg.ini

REPORT_CMD = 0x05       # 6 bytes (1B Report ID + 5B payload)
REPORT_DATA = 0x06      # 1032 bytes (0x408: 1B Report ID + 1031B payload)
REPORT_LIVE_RGB = 0x08  # 382 bytes (0x17E: 1B Report ID + 381B payload)

PROFILE_DATA_SIZE = 136  # 0x88 bytes (8B global + 128B profile data)
PROFILE_PRO1_OFFSET = 8
PROFILE_EFFECT_OFFSET = 4  # gVar 0x5e1662 default = 4
PROFILE_MAGIC = bytes([0x5A, 0xA5])

LED_MATRIX_PLANE_SIZE = 0x7E  # 126 LED slots per R/G/B plane

# Exact 22 LED modes from Cfg.ini (LedOpt1..22: col 1 = hw code written to pro1[5], col 2 = UI effect ID) and text.xml
LED_MODES: list[dict[str, Any]] = [
    {"id": "fixed_on", "slot": 1, "hw_effect": 1, "ui_effect": 23, "name": "Cor Fixa", "has_speed": False, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "respire", "slot": 2, "hw_effect": 2, "ui_effect": 31, "name": "Respiração", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "rainbow", "slot": 3, "hw_effect": 3, "ui_effect": 2, "name": "Arco-Íris", "has_speed": True, "has_brightness": True, "has_random": False, "has_color": False},
    {"id": "flash_away", "slot": 4, "hw_effect": 4, "ui_effect": 19, "name": "Rastro ao Digitar", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "raindrops", "slot": 5, "hw_effect": 5, "ui_effect": 15, "name": "Gotas de Chuva", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "rainbow_wheel", "slot": 6, "hw_effect": 6, "ui_effect": 13, "name": "Roda Arco-Íris", "has_speed": True, "has_brightness": True, "has_random": False, "has_color": False},
    {"id": "ripples", "slot": 7, "hw_effect": 7, "ui_effect": 20, "name": "Ondas ao Toque", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "stars", "slot": 8, "hw_effect": 8, "ui_effect": 16, "name": "Estrelas Cintilantes", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "shadow", "slot": 9, "hw_effect": 9, "ui_effect": 18, "name": "Sombra Desvanecendo", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "retro_snake", "slot": 10, "hw_effect": 10, "ui_effect": 5, "name": "Serpente Retrô", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "neon_stream", "slot": 11, "hw_effect": 11, "ui_effect": 7, "name": "Fluxo Neon", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "reaction", "slot": 12, "hw_effect": 12, "ui_effect": 17, "name": "Reação Instantânea", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "sine_wave", "slot": 13, "hw_effect": 13, "ui_effect": 12, "name": "Onda Senoidal", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "scanning", "slot": 14, "hw_effect": 14, "ui_effect": 8, "name": "Varredura", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "windmill", "slot": 15, "hw_effect": 15, "ui_effect": 28, "name": "Catavento Giratório", "has_speed": True, "has_brightness": True, "has_random": False, "has_color": False},
    {"id": "waterfall", "slot": 16, "hw_effect": 16, "ui_effect": 30, "name": "Cascata Colorida", "has_speed": True, "has_brightness": True, "has_random": False, "has_color": False},
    {"id": "blossoming", "slot": 17, "hw_effect": 17, "ui_effect": 9, "name": "Desabrochar", "has_speed": True, "has_brightness": True, "has_random": False, "has_color": False},
    {"id": "storm", "slot": 18, "hw_effect": 18, "ui_effect": 29, "name": "Tempestade Giratória", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "collision", "slot": 19, "hw_effect": 19, "ui_effect": 27, "name": "Colisão", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "perfect", "slot": 20, "hw_effect": 20, "ui_effect": 26, "name": "Espectro Suave", "has_speed": True, "has_brightness": True, "has_random": True, "has_color": True},
    {"id": "custom", "slot": 21, "hw_effect": 21, "ui_effect": 0, "name": "Personalizado por Tecla", "has_speed": False, "has_brightness": True, "has_random": False, "has_color": True, "is_custom": True},
    {"id": "off", "slot": 22, "hw_effect": 0, "ui_effect": 0, "name": "Desligado", "has_speed": False, "has_brightness": False, "has_random": False, "has_color": False},
]

LED_MODE_BY_ID: dict[str, dict[str, Any]] = {m["id"]: m for m in LED_MODES}
LED_MODE_BY_HW: dict[int, dict[str, Any]] = {
    m["hw_effect"]: m for m in LED_MODES if m["hw_effect"] != 0
}

DEFAULT_COLOR_PALETTE: list[str] = [
    "#ff1e3c",  # Vermelho Redragon
    "#ff7a00",  # Laranja
    "#ffd500",  # Amarelo
    "#00e676",  # Verde
    "#00e5ff",  # Ciano
    "#2979ff",  # Azul
    "#d500f9",  # Roxo
]


def load_key_layout() -> list[dict[str, Any]]:
    dump_path = Path(__file__).resolve().parents[1] / "assets" / "k653_rea_dump.json"
    if dump_path.exists():
        try:
            data = json.loads(dump_path.read_text(encoding="utf-8"))
            keys = data.get("cfg", {}).get("keys", [])
            if isinstance(keys, list) and keys:
                return keys
        except Exception:
            pass
    return []


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    s = str(hex_color or "#ff1e3c").strip().lstrip("#")
    if len(s) != 6:
        return (255, 30, 60)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return (255, 30, 60)


def default_config() -> dict[str, Any]:
    # Default per-key custom map: highlight WASD + Arrows in red, rest subtle cyan
    wasd_arrows = {
        "W": "#ff1e3c", "A": "#ff1e3c", "S": "#ff1e3c", "D": "#ff1e3c",
        "Up": "#ff1e3c", "Down": "#ff1e3c", "Left": "#ff1e3c", "Right": "#ff1e3c",
        "Esc": "#ff1e3c",
    }
    custom_colors: dict[str, str] = {}
    for k in load_key_layout():
        lbl = str(k.get("label", ""))
        custom_colors[k["id"]] = wasd_arrows.get(lbl, "#00e5ff")

    return {
        "profile_id": 1,           # 1..3
        "led_mode": "rainbow",     # One of LED_MODES[*]["id"]
        "brightness": 4,           # 0..4
        "speed": 3,                # 0..4
        "direction": 0,            # 0 or 1
        "colorful": True,          # True -> color_index = 7 (rainbow/random)
        "color_index": 0,          # 0..6 index in palette
        "color_hex": "#ff1e3c",    # Primary color (synced into palette[color_index])
        "palette": list(DEFAULT_COLOR_PALETTE),
        "custom_slot": 0,          # 0..4 (Define1..5)
        "custom_key_colors": custom_colors,
    }


def build_get_password_req() -> bytes:
    """SET_FEATURE Report 0x05 (6B) requesting 6-byte device password (PSD)."""
    return bytes([REPORT_CMD, 0x05, 0x81, 0x00, 0x00, 0x00])


def parse_password_resp(raw: bytes) -> dict[str, Any] | None:
    if not raw or len(raw) < 6:
        return None
    offset = 1 if raw[0] == REPORT_CMD else 0
    if len(raw) < offset + 2:
        return None
    status = raw[offset]
    psd = raw[offset + 1 : offset + 7]
    return {
        "ok": status == 0x01,
        "status": status,
        "psd": list(psd),
        "psd_hex": psd.hex(" "),
        "matches_k653": psd[: len(K653_PSD)] == K653_PSD if len(psd) >= len(K653_PSD) else False,
    }


def build_get_profile_req() -> bytes:
    """SET_FEATURE Report 0x05 (6B) requesting 136-byte hardware profile via Report 0x06."""
    return bytes([REPORT_CMD, 0x83, 0xC6, 0x00, 0x00, 0x00])


def build_set_profile_report(cfg: dict[str, Any], base_profile: bytes | None = None) -> bytes:
    """
    Build 1032-byte (0x408) Feature Report 0x06 for SetProfile (0x445490 + 0x40d150).
    Header: [0x06, 0x03, 0xC6, 0x00, 0x00, 0x00, 0x00, 0x00]
    Payload: 136 bytes (8B global + 128B pro1) + zero padding to 1032 bytes.
    Note: KeyboardDrv.exe always writes prof[0] = 0x00 (active hardware slot 0), while
    Perfil 1/2/3 are managed as software profiles in the app and applied to slot 0.
    """
    if base_profile and len(base_profile) >= PROFILE_DATA_SIZE:
        prof = bytearray(base_profile[:PROFILE_DATA_SIZE])
    else:
        prof = bytearray(PROFILE_DATA_SIZE)
        prof[6] = 0x5A
        prof[7] = 0xA5
        prof[PROFILE_PRO1_OFFSET : PROFILE_PRO1_OFFSET + 4] = bytes([0x03, 0x03, 0x03, 0x00])

    # Hardware slot is always 0 (0x5e0c05 = OurCfg = 0 in KeyboardDrv.exe)
    prof[0] = 0x00

    pro1 = bytearray(prof[PROFILE_PRO1_OFFSET : PROFILE_PRO1_OFFSET + 64])
    if len(pro1) < 64:
        pro1.extend(bytes(64 - len(pro1)))

    mode_id = str(cfg.get("led_mode", "rainbow"))
    mode_info = LED_MODE_BY_ID.get(mode_id, LED_MODE_BY_ID["rainbow"])
    is_custom = bool(mode_info.get("is_custom", False))
    hw_effect = int(mode_info["hw_effect"])

    pro1[PROFILE_EFFECT_OFFSET] = 0x01 if is_custom else 0x00
    pro1[PROFILE_EFFECT_OFFSET + 1] = hw_effect & 0xFF
    pro1[PROFILE_EFFECT_OFFSET + 2] = max(0, min(4, int(cfg.get("custom_slot", 0))))
    pro1[0x14] = 0xFF
    pro1[0x15] = 0xFF

    brightness = max(0, min(4, int(cfg.get("brightness", 4))))
    speed = max(0, min(4, int(cfg.get("speed", 3))))
    direction = 1 if int(cfg.get("direction", 0)) else 0
    supports_color = bool(mode_info.get("has_color", False))
    colorful = True if not supports_color else bool(cfg.get("colorful", True))
    color_idx = 0x07 if colorful else max(0, min(6, int(cfg.get("color_index", 0))))
    dir_nibble = 0x08 if direction else 0x00
    byte0 = (dir_nibble << 4) | (color_idx & 0x0F)
    byte1 = ((speed & 0x0F) << 4) | (brightness & 0x0F)

    # Populate all 20 LED mode parameter slots (0x16..0x3D) consistently
    for idx in range(20):
        pos = 0x16 + idx * 2
        if pro1[pos] == 0 and pro1[pos + 1] == 0:
            pro1[pos] = 0x07
            pro1[pos + 1] = 0x44
    if 1 <= mode_info["slot"] <= 20:
        active_pos = 0x16 + (mode_info["slot"] - 1) * 2
        pro1[active_pos] = byte0
        pro1[active_pos + 1] = byte1
    else:
        # Apply brightness/color defaults to slot 0 as well for consistency
        pro1[0x16] = byte0
        pro1[0x17] = byte1

    pro1[0x3E] = 0x5A
    pro1[0x3F] = 0xA5

    prof[PROFILE_PRO1_OFFSET : PROFILE_PRO1_OFFSET + 64] = pro1

    report = bytearray(1032)
    report[0] = REPORT_DATA
    report[1] = 0x03
    report[2] = 0xC6
    report[8 : 8 + PROFILE_DATA_SIZE] = prof
    return bytes(report)


def parse_profile_report(raw: bytes) -> dict[str, Any] | None:
    """Parse 1032-byte Feature Report 0x06 response from GetProfile (0x4455a0)."""
    if not raw or len(raw) < 8 + PROFILE_DATA_SIZE:
        return None
    if raw[0] != REPORT_DATA:
        return None
    if raw[1] not in (0x83, 0x03):
        return None

    prof = raw[8 : 8 + PROFILE_DATA_SIZE]
    pro1 = prof[PROFILE_PRO1_OFFSET : PROFILE_PRO1_OFFSET + 64]
    is_custom = pro1[PROFILE_EFFECT_OFFSET] == 0x01
    hw_effect = pro1[PROFILE_EFFECT_OFFSET + 1]
    custom_slot = int(pro1[PROFILE_EFFECT_OFFSET + 2]) % 5

    if is_custom or hw_effect == 21:
        mode_info = LED_MODE_BY_ID["custom"]
    elif hw_effect == 0:
        mode_info = LED_MODE_BY_ID["off"]
    else:
        mode_info = LED_MODE_BY_HW.get(hw_effect, LED_MODE_BY_ID["rainbow"])

    slot = mode_info["slot"]
    param_idx = (slot - 1) if 1 <= slot <= 20 else 0
    b0 = pro1[0x16 + param_idx * 2]
    b1 = pro1[0x16 + param_idx * 2 + 1]

    color_nibble = b0 & 0x0F
    dir_nibble = (b0 >> 4) & 0x0F
    brightness = min(4, b1 & 0x0F)
    speed = min(4, (b1 >> 4) & 0x0F)

    return {
        "profile_id": max(1, min(3, int(prof[0]) + 1)),
        "led_mode": mode_info["id"],
        "hw_effect": hw_effect,
        "custom_slot": custom_slot,
        "brightness": brightness,
        "speed": speed,
        "direction": 1 if dir_nibble >= 8 else 0,
        "colorful": color_nibble == 0x07,
        "color_index": 0 if color_nibble == 0x07 else min(6, color_nibble),
        "magic_ok": pro1[0x3E:0x40] == PROFILE_MAGIC,
        "raw_profile": prof,
    }


def build_set_rgb_table_report(cfg: dict[str, Any]) -> bytes:
    """
    Build 1032-byte Feature Report 0x06 for SetLedRgbTab (0x4459f0 + 0x40d44b).
    Header: [0x06, 0x08, 0xC8, 0x00, 0x40, 0x00, 0x00, 0x00]
    Payload: 21 zero bytes (offset 8..28), followed by 20 modes * 7 RGB triplets (420 bytes).
    """
    palette = list(cfg.get("palette") or DEFAULT_COLOR_PALETTE)
    while len(palette) < 7:
        palette.append(DEFAULT_COLOR_PALETTE[len(palette)])

    color_idx = max(0, min(6, int(cfg.get("color_index", 0))))
    if cfg.get("color_hex"):
        palette[color_idx] = str(cfg["color_hex"])

    rgb_7 = bytearray()
    for hex_c in palette[:7]:
        r, g, b = _hex_to_rgb(hex_c)
        rgb_7.extend([r, g, b])

    report = bytearray(1032)
    report[0] = REPORT_DATA
    report[1] = 0x08
    report[2] = 0xC8
    report[3] = 0x00
    report[4] = 0x40

    # 21 zero bytes padding (0x445a59..0x445a6d), then 20 modes * 21 bytes
    base = 8 + 21
    for m_idx in range(20):
        off = base + m_idx * 21
        report[off : off + 21] = rgb_7
    return bytes(report)


def _pack_per_key_planes(cfg: dict[str, Any]) -> bytes:
    """Pack per-key RGB colors into 3 planar arrays of 126 (0x7E) bytes: R[126], G[126], B[126]."""
    planes = bytearray(LED_MATRIX_PLANE_SIZE * 3)
    custom_map = cfg.get("custom_key_colors") or {}
    fallback_rgb = _hex_to_rgb(str(cfg.get("color_hex", "#00e5ff")))

    for k in load_key_layout():
        led_idx = int(k.get("led_idx", -1))
        if 0 <= led_idx < LED_MATRIX_PLANE_SIZE:
            hex_c = custom_map.get(k["id"])
            r, g, b = _hex_to_rgb(hex_c) if hex_c else fallback_rgb
            planes[led_idx] = r
            planes[LED_MATRIX_PLANE_SIZE + led_idx] = g
            planes[LED_MATRIX_PLANE_SIZE * 2 + led_idx] = b
    return bytes(planes)


def build_set_led_matrix_reports(cfg: dict[str, Any]) -> list[bytes]:
    """
    Build the two 1032-byte Feature Report 0x06 frames for SetLedMatrix (0x4456e0, pages 0xCC & 0xD0).
    Stores 5 custom per-key lighting slots (each 3 * 0x7E = 378 bytes -> total 1890 bytes across 2 pages).
    """
    single_slot = _pack_per_key_planes(cfg)  # 378 bytes
    full_buf = bytearray(2048)
    for slot in range(5):
        off = slot * len(single_slot)
        full_buf[off : off + len(single_slot)] = single_slot

    reports: list[bytes] = []
    for page_code, slice_off in ((0xCC, 0), (0xD0, 1024)):
        rep = bytearray(1032)
        rep[0] = REPORT_DATA
        rep[1] = 0x09
        rep[2] = page_code
        rep[3] = 0x00
        rep[4] = 0x40
        rep[8 : 8 + 1024] = full_buf[slice_off : slice_off + 1024]
        reports.append(bytes(rep))
    return reports


def build_live_rgb_report(cfg: dict[str, Any]) -> bytes:
    """
    Build 382-byte (0x17E) Feature Report 0x08 for instant per-key live RGB (SendMusicRGB 0x445c30).
    Header: [0x08, 0x0A, 0x7A, 0x01] + 378 bytes planar RGB.
    """
    planes = _pack_per_key_planes(cfg)
    rep = bytearray(382)
    rep[0] = REPORT_LIVE_RGB
    rep[1] = 0x0A
    rep[2] = 0x7A
    rep[3] = 0x01
    rep[4 : 4 + len(planes)] = planes
    return bytes(rep)


def read_hardware_state(sess: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read current password verification and active profile/LED settings from wired K653-RGB-PRO."""
    logs: list[dict[str, Any]] = []
    state: dict[str, Any] = {}

    ok_pw_tx, _, detail_pw_tx = sess.set_feature_report(REPORT_CMD, build_get_password_req())
    logs.append({"op": "get_password_req", "ok": ok_pw_tx, "detail": detail_pw_tx})
    if ok_pw_tx:
        time.sleep(0.025)
        ok_pw_rx, _, raw_pw, detail_pw_rx = sess.get_feature_report(REPORT_CMD, 6)
        parsed_pw = parse_password_resp(raw_pw) if ok_pw_rx else None
        logs.append({"op": "get_password_resp", "ok": ok_pw_rx, "detail": detail_pw_rx})
        if parsed_pw:
            state["psd_ok"] = parsed_pw["ok"]

    ok_pr_tx, _, detail_pr_tx = sess.set_feature_report(REPORT_CMD, build_get_profile_req())
    logs.append({"op": "get_profile_req", "ok": ok_pr_tx, "detail": detail_pr_tx})
    if ok_pr_tx:
        time.sleep(0.025)
        ok_pr_rx, _, raw_pr, detail_pr_rx = sess.get_feature_report(REPORT_DATA, 1032)
        parsed_pr = parse_profile_report(raw_pr) if ok_pr_rx else None
        logs.append({"op": "get_profile_resp", "ok": ok_pr_rx, "detail": detail_pr_rx})
        if parsed_pr:
            for k in ("profile_id", "led_mode", "custom_slot", "brightness", "speed", "direction", "colorful", "color_index"):
                state[k] = parsed_pr[k]
    return state, logs


def apply_config(sess: Any, cfg: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """
    Apply full lighting & profile configuration to Redragon K653-RGB-PRO wired USB-C (0x258A:0x0049),
    following KeyboardDrv.exe's exact sequence: GetProfile -> SetLedRgbTab -> (SetLedMatrix if custom) -> SetProfile.
    """
    logs: list[dict[str, Any]] = []
    base_prof: bytes | None = None

    ok_r, _, detail_r = sess.set_feature_report(REPORT_CMD, build_get_profile_req())
    if ok_r:
        time.sleep(0.025)
        ok_g, _, raw_g, detail_g = sess.get_feature_report(REPORT_DATA, 1032)
        if ok_g:
            parsed = parse_profile_report(raw_g)
            if parsed and isinstance(parsed.get("raw_profile"), (bytes, bytearray)):
                base_prof = bytes(parsed["raw_profile"])
        logs.append({"op": "read_base_profile", "ok": ok_g, "detail": detail_g})
    else:
        logs.append({"op": "read_base_profile_req", "ok": False, "detail": detail_r})

    # 1) Color palette table (0x08 0xC8)
    rgb_tab = build_set_rgb_table_report(cfg)
    ok_tab, _, detail_tab = sess.set_feature_report(REPORT_DATA, rgb_tab)
    logs.append({"op": "set_led_rgb_table", "ok": ok_tab, "detail": detail_tab})
    time.sleep(0.04)

    # 2) Custom per-key RGB matrix if custom mode is selected (0x09 0xCC / 0xD0)
    if str(cfg.get("led_mode")) == "custom":
        for idx, mat_rep in enumerate(build_set_led_matrix_reports(cfg)):
            ok_m, _, detail_m = sess.set_feature_report(REPORT_DATA, mat_rep)
            logs.append({"op": f"set_led_matrix_{idx}", "ok": ok_m, "detail": detail_m})
            time.sleep(0.04)

    # 3) Save active profile + LED effect/brightness/speed/color (0x03 0xC6)
    prof_rep = build_set_profile_report(cfg, base_profile=base_prof)
    ok_prof, _, detail_prof = sess.set_feature_report(REPORT_DATA, prof_rep)
    logs.append({"op": "set_profile", "ok": ok_prof, "detail": detail_prof})
    time.sleep(0.025)

    all_ok = ok_tab and ok_prof
    return all_ok, logs
