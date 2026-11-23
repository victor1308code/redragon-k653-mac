#!/usr/bin/env python3
"""Byte-exact unit tests for Redragon K653-RGB-PRO (KeyboardDrv.exe) protocol."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from protocols import k653_protocol


class TestK653Protocol(unittest.TestCase):
    def test_password_request_and_response(self) -> None:
        req = k653_protocol.build_get_password_req()
        self.assertEqual(req, bytes([0x05, 0x05, 0x81, 0x00, 0x00, 0x00]))

        rx = bytes([0x05, 0x01, 0x02, 0x00, 0x00, 0x00, 0x01, 0x23])
        parsed = k653_protocol.parse_password_resp(rx)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertTrue(parsed["ok"])
        self.assertTrue(parsed["matches_k653"])

    def test_profile_build_and_parse_roundtrip(self) -> None:
        cfg = k653_protocol.default_config()
        cfg.update(
            {
                "profile_id": 2,
                "led_mode": "neon_stream",  # slot 11, hw_effect = 11 (Col 1 of LedOpt11)
                "brightness": 3,
                "speed": 4,
                "direction": 1,
                "colorful": False,
                "color_index": 5,
            }
        )
        rep = k653_protocol.build_set_profile_report(cfg)
        self.assertEqual(len(rep), 1032)
        self.assertEqual(rep[:3], bytes([0x06, 0x03, 0xC6]))
        # Hardware profile slot byte prof[0] must always stay 0x00 (matching KeyboardDrv.exe)
        self.assertEqual(rep[8], 0x00)
        # Check Pro1 signature 0x5A 0xA5 at offset 8 + 8 + 0x3E = 78
        self.assertEqual(rep[78:80], bytes([0x5A, 0xA5]))

        # Simulate hardware GetProfile response (byte 1 = 0x83)
        rx = bytearray(rep)
        rx[1] = 0x83
        parsed = k653_protocol.parse_profile_report(bytes(rx))
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertTrue(parsed["magic_ok"])
        self.assertEqual(parsed["led_mode"], "neon_stream")
        self.assertEqual(parsed["hw_effect"], 11)
        self.assertEqual(parsed["brightness"], 3)
        self.assertEqual(parsed["speed"], 4)
        self.assertEqual(parsed["direction"], 1)
        self.assertFalse(parsed["colorful"])
        self.assertEqual(parsed["color_index"], 5)

    def test_custom_mode_and_off_mode(self) -> None:
        cfg = k653_protocol.default_config()
        cfg["led_mode"] = "custom"
        cfg["custom_slot"] = 3
        rep = k653_protocol.build_set_profile_report(cfg)
        parsed = k653_protocol.parse_profile_report(rep)
        assert parsed is not None
        self.assertEqual(parsed["led_mode"], "custom")
        self.assertEqual(parsed["hw_effect"], 21)
        self.assertEqual(parsed["custom_slot"], 3)

        cfg["led_mode"] = "off"
        rep_off = k653_protocol.build_set_profile_report(cfg)
        parsed_off = k653_protocol.parse_profile_report(rep_off)
        assert parsed_off is not None
        self.assertEqual(parsed_off["led_mode"], "off")
        self.assertEqual(parsed_off["hw_effect"], 0)

    def test_rgb_table_led_matrix_and_live_rgb(self) -> None:
        cfg = k653_protocol.default_config()
        cfg["color_index"] = 0
        cfg["color_hex"] = "#123456"
        tab = k653_protocol.build_set_rgb_table_report(cfg)
        self.assertEqual(len(tab), 1032)
        self.assertEqual(tab[:5], bytes([0x06, 0x08, 0xC8, 0x00, 0x40]))
        # 21 zero bytes then first mode's first color = 0x12, 0x34, 0x56
        self.assertEqual(tab[8:29], bytes(21))
        self.assertEqual(tab[29:32], bytes([0x12, 0x34, 0x56]))

        mats = k653_protocol.build_set_led_matrix_reports(cfg)
        self.assertEqual(len(mats), 2)
        self.assertEqual(len(mats[0]), 1032)
        self.assertEqual(mats[0][:5], bytes([0x06, 0x09, 0xCC, 0x00, 0x40]))
        self.assertEqual(mats[1][:5], bytes([0x06, 0x09, 0xD0, 0x00, 0x40]))

        live = k653_protocol.build_live_rgb_report(cfg)
        self.assertEqual(len(live), 382)
        self.assertEqual(live[:4], bytes([0x08, 0x0A, 0x7A, 0x01]))
        # Esc key is led_idx=0 -> default wasd_arrows "#ff1e3c"
        self.assertEqual((live[4], live[4 + 126], live[4 + 252]), (0xFF, 0x1E, 0x3C))

    def test_key_layout_loaded_96_keys(self) -> None:
        keys = k653_protocol.load_key_layout()
        self.assertEqual(len(keys), 96)
        esc = next(k for k in keys if k["id"] == "K1")
        self.assertEqual(esc["label"], "Esc")
        self.assertEqual(esc["led_idx"], 0)


if __name__ == "__main__":
    unittest.main()
