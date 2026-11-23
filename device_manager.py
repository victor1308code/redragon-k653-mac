#!/usr/bin/env python3
"""
Unified plug-and-play device manager for Redragon K653-RGB-PRO on macOS.
Handles Wired USB-C configuration (0x258A:0x0049), 2.4G detection (0x25A7:0xFA70),
Bluetooth battery monitoring, profile persistence, and background auto-sync.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import threading
import time
from pathlib import Path
from typing import Any

import hid_bridge
from protocols import k653_protocol

STATE_DIR = Path.home() / ".redragon_k653_mac"
STATE_FILE = STATE_DIR / "state.json"

_LOCK = threading.RLock()
_MONITOR_STARTED = False
_MONITOR_LOCK = threading.Lock()


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _default_profiles() -> dict[str, dict[str, Any]]:
    p1 = k653_protocol.default_config()
    p1["profile_id"] = 1
    p1["led_mode"] = "rainbow"
    p1["colorful"] = True

    p2 = k653_protocol.default_config()
    p2["profile_id"] = 2
    p2["led_mode"] = "fixed_on"
    p2["colorful"] = False
    p2["color_index"] = 0
    p2["color_hex"] = "#ff1e3c"

    p3 = k653_protocol.default_config()
    p3["profile_id"] = 3
    p3["led_mode"] = "respire"
    p3["colorful"] = False
    p3["color_index"] = 4
    p3["color_hex"] = "#00e5ff"

    return {"1": p1, "2": p2, "3": p3}


def _default_state() -> dict[str, Any]:
    profiles = _default_profiles()
    return {
        "config": copy.deepcopy(profiles["1"]),
        "profiles": profiles,
        "pending_sync": False,
        "telemetry": {
            "battery": {
                "percent": None,
                "charging": False,
                "mode": "unknown",
                "label": "Aguardando conexão",
                "hint": "",
            },
        },
        "last_sync": {
            "ok": None,
            "timestamp": None,
            "hardware_synced": False,
            "message": "Pronto para configurar seu Redragon K653-RGB-PRO.",
            "logs": [],
        },
    }


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_state() -> dict[str, Any]:
    with _LOCK:
        defaults = _default_state()
        if not STATE_FILE.exists():
            return defaults
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return _deep_merge(defaults, raw)
        except Exception:
            pass
        return defaults


def save_state(state: dict[str, Any]) -> None:
    with _LOCK:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _compute_battery_status(
    devices: list[hid_bridge.KeyboardDeviceInfo], prev_battery: dict[str, Any]
) -> dict[str, Any]:
    wired = next((d for d in devices if d.connection_mode == "wired"), None)
    bt = next((d for d in devices if d.connection_mode == "bluetooth"), None)
    d24 = next((d for d in devices if d.connection_mode == "24g"), None)

    if bt is not None and bt.battery_percent is not None:
        return {
            "percent": int(bt.battery_percent),
            "charging": wired is not None,
            "mode": "bluetooth",
            "label": "Carregando • Bluetooth" if wired is not None else "Sem fio • Bluetooth",
            "hint": "Leitura em tempo real pelo macOS.",
        }

    if wired is not None:
        return {
            "percent": prev_battery.get("percent"),
            "charging": True,
            "mode": "wired",
            "label": "Carregando via Cabo USB-C",
            "hint": "Modo cabo ativo — todas as configurações de RGB e perfil são aplicadas na hora.",
        }

    if d24 is not None:
        return {
            "percent": None,
            "charging": False,
            "mode": "24g",
            "label": "Conectado via Receptor 2.4G",
            "hint": "No modo 2.4G o receptor não informa a %. Use Bluetooth (FN+1) para ver a % exata ou conecte o cabo USB-C para aplicar iluminação.",
        }

    return {
        "percent": None,
        "charging": False,
        "mode": "disconnected",
        "label": "Teclado desconectado",
        "hint": "Conecte o cabo USB-C, o receptor 2.4G ou pareie via Bluetooth.",
    }


def get_status(read_hw: bool = False) -> dict[str, Any]:
    with _LOCK:
        state = load_state()
        devices = hid_bridge.enumerate_k653_devices()
        wired = next((d for d in devices if d.connection_mode == "wired"), None)
        primary = devices[0] if devices else None

        bat = _compute_battery_status(devices, state["telemetry"].get("battery") or {})
        state["telemetry"]["battery"] = bat
        probe_logs: list[dict[str, Any]] = []

        if wired is not None and read_hw:
            try:
                with hid_bridge.K653HidSession(wired.location_id) as sess:
                    hw_state, probe_logs = k653_protocol.read_hardware_state(sess)
                    if hw_state:
                        for k in ("led_mode", "custom_slot", "brightness", "speed", "direction", "colorful", "color_index"):
                            if k in hw_state:
                                state["config"][k] = hw_state[k]
                        palette = state["config"].get("palette") or k653_protocol.DEFAULT_COLOR_PALETTE
                        cidx = int(state["config"].get("color_index", 0))
                        if 0 <= cidx < len(palette):
                            state["config"]["color_hex"] = palette[cidx]
                        pid_key = str(max(1, min(3, int(state["config"].get("profile_id", 1)))))
                        state.setdefault("profiles", _default_profiles())[pid_key] = copy.deepcopy(state["config"])
            except Exception as exc:
                probe_logs.append({"op": "read_hw", "ok": False, "detail": str(exc)})

        save_state(state)

        return {
            "connected_devices": [d.to_dict() for d in devices],
            "connected_device": primary.to_dict() if primary else None,
            "wired_connected": wired is not None,
            "pending_sync": bool(state.get("pending_sync", False)),
            "config": state["config"],
            "led_modes": k653_protocol.LED_MODES,
            "keys": k653_protocol.load_key_layout(),
            "telemetry": state["telemetry"],
            "last_sync": state["last_sync"],
            "probe_logs": probe_logs,
        }


def apply_settings(updates: dict[str, Any] | None = None, reset_defaults: bool = False) -> dict[str, Any]:
    with _LOCK:
        state = load_state()
        devices = hid_bridge.enumerate_k653_devices()
        wired = next((d for d in devices if d.connection_mode == "wired"), None)
        profiles = state.setdefault("profiles", _default_profiles())

        if reset_defaults:
            profiles = _default_profiles()
            state["profiles"] = profiles
            cfg = copy.deepcopy(profiles["1"])
        elif updates and updates.get("switch_profile"):
            # Save current profile before switching
            cur_pid = str(max(1, min(3, int(state["config"].get("profile_id", 1)))))
            profiles[cur_pid] = copy.deepcopy(state["config"])
            new_pid = max(1, min(3, int(updates.get("profile_id", 1))))
            cfg = copy.deepcopy(profiles.get(str(new_pid)) or _default_profiles()[str(new_pid)])
            cfg["profile_id"] = new_pid
        else:
            cfg = copy.deepcopy(state["config"])
            if updates:
                clean_updates = {k: v for k, v in updates.items() if k != "switch_profile"}
                cfg = _deep_merge(cfg, clean_updates)

        cfg["profile_id"] = max(1, min(3, int(cfg.get("profile_id", 1))))
        cfg["brightness"] = max(0, min(4, int(cfg.get("brightness", 4))))
        cfg["speed"] = max(0, min(4, int(cfg.get("speed", 3))))
        cfg["direction"] = 1 if int(cfg.get("direction", 0)) else 0
        cfg["custom_slot"] = max(0, min(4, int(cfg.get("custom_slot", 0))))
        palette = list(cfg.get("palette") or k653_protocol.DEFAULT_COLOR_PALETTE)
        while len(palette) < 7:
            palette.append(k653_protocol.DEFAULT_COLOR_PALETTE[len(palette)])
        cidx = max(0, min(6, int(cfg.get("color_index", 0))))
        cfg["color_index"] = cidx
        if cfg.get("color_hex"):
            palette[cidx] = str(cfg["color_hex"])
        cfg["palette"] = palette[:7]
        state["config"] = cfg
        profiles[str(cfg["profile_id"])] = copy.deepcopy(cfg)
        state["profiles"] = profiles

        if wired is None:
            state["pending_sync"] = True
            has_24g = any(d.connection_mode == "24g" for d in devices)
            msg = (
                "Preferências salvas! Conecte o cabo USB-C do teclado para gravar a iluminação no K653."
                if has_24g
                else "Preferências salvas — serão aplicadas automaticamente quando o teclado for conectado via USB-C."
            )
            sync_info = {
                "ok": False,
                "timestamp": _now_iso(),
                "hardware_synced": False,
                "message": msg,
                "logs": [],
            }
            state["last_sync"] = sync_info
            save_state(state)
            res = get_status(read_hw=False)
            res["apply_result"] = sync_info
            return res

        hw_ok = False
        logs: list[dict[str, Any]] = []
        try:
            with hid_bridge.K653HidSession(wired.location_id) as sess:
                hw_ok, logs = k653_protocol.apply_config(sess, cfg)
            if hw_ok:
                state["pending_sync"] = False
                msg = "Iluminação e perfil aplicados no teclado."
            else:
                state["pending_sync"] = True
                msg = "Salvo localmente — tentando novamente em instantes."
        except Exception as exc:
            state["pending_sync"] = True
            logs.append({"op": "apply_error", "ok": False, "detail": str(exc)})
            msg = "Salvo localmente — conecte o cabo USB-C diretamente para concluir."

        sync_info = {
            "ok": hw_ok,
            "timestamp": _now_iso(),
            "hardware_synced": hw_ok,
            "message": msg,
            "logs": logs,
        }
        state["last_sync"] = sync_info
        save_state(state)
        res = get_status(read_hw=False)
        res["apply_result"] = sync_info
        return res


def send_live_rgb(custom_key_colors: dict[str, str] | None = None) -> dict[str, Any]:
    """Send live per-key RGB preview via Report 0x08 when connected over USB-C."""
    with _LOCK:
        state = load_state()
        if custom_key_colors:
            state["config"]["custom_key_colors"] = _deep_merge(
                state["config"].get("custom_key_colors") or {}, custom_key_colors
            )
            save_state(state)
        devices = hid_bridge.enumerate_k653_devices()
        wired = next((d for d in devices if d.connection_mode == "wired"), None)
        if wired is None:
            return {"ok": False, "message": "Conecte o cabo USB-C para pré-visualizar em tempo real."}
        try:
            with hid_bridge.K653HidSession(wired.location_id) as sess:
                rep = k653_protocol.build_live_rgb_report(state["config"])
                ok, _, detail = sess.set_feature_report(k653_protocol.REPORT_LIVE_RGB, rep)
            return {"ok": ok, "detail": detail}
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}


def _monitor_step() -> None:
    if not _LOCK.acquire(blocking=False):
        return
    try:
        devices = hid_bridge.enumerate_k653_devices()
        state = load_state()
        bat = _compute_battery_status(devices, state["telemetry"].get("battery") or {})
        changed = bat != state["telemetry"].get("battery")
        state["telemetry"]["battery"] = bat

        wired = next((d for d in devices if d.connection_mode == "wired"), None)
        if wired is not None and state.get("pending_sync"):
            try:
                with hid_bridge.K653HidSession(wired.location_id) as sess:
                    hw_ok, logs = k653_protocol.apply_config(sess, state["config"])
                if hw_ok:
                    state["pending_sync"] = False
                    state["last_sync"] = {
                        "ok": True,
                        "timestamp": _now_iso(),
                        "hardware_synced": True,
                        "message": "Iluminação e perfil aplicados automaticamente no teclado.",
                        "logs": logs,
                    }
                    changed = True
            except Exception:
                pass
        if changed:
            save_state(state)
    except Exception:
        pass
    finally:
        _LOCK.release()


def _monitor_loop() -> None:
    while True:
        _monitor_step()
        time.sleep(3.0)


def start_background_monitor() -> None:
    global _MONITOR_STARTED
    with _MONITOR_LOCK:
        if _MONITOR_STARTED:
            return
        _MONITOR_STARTED = True
        t = threading.Thread(target=_monitor_loop, name="RedragonK653Monitor", daemon=True)
        t.start()
