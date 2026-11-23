#!/usr/bin/env python3
"""
Native macOS IOKit.framework + CoreFoundation.framework HID Bridge for Redragon K653-RGB-PRO.
Supports Wired USB-C config (0x258A:0x0049), 2.4G Wireless detection (0x25A7:0xFA70),
and macOS native Bluetooth keyboard battery telemetry.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any

kCFAllocatorDefault = None
kCFStringEncodingUTF8 = 0x08000100
kCFNumberSInt64Type = 4
kIOHIDOptionsTypeNone = 0
kIOHIDReportTypeInput = 0
kIOHIDReportTypeOutput = 1
kIOHIDReportTypeFeature = 2
kIOReturnSuccess = 0

K653_WIRED_VID = 0x258A
K653_WIRED_PID = 0x0049

K653_24G_VID = 0x25A7
K653_24G_PID = 0xFA70

IORETURN_NAMES = {
    0x00000000: "kIOReturnSuccess",
    0xE00002BC: "kIOReturnError",
    0xE00002C1: "kIOReturnNoDevice",
    0xE00002C2: "kIOReturnBadArgument",
    0xE00002C5: "kIOReturnExclusiveAccess",
    0xE00002D6: "kIOReturnTimeout",
    0xE00002D8: "kIOReturnNotReady",
    0xE00002ED: "kIOReturnNotResponding",
    0xE000404F: "kIOUSBTransactionTimeout",
    0xE0005000: "kIOUSBPipeStalled",
}


def format_ioreturn(code: int) -> str:
    ucode = code & 0xFFFFFFFF
    name = IORETURN_NAMES.get(ucode, "IOReturn")
    return f"0x{ucode:08x} ({name})"


_cf: ctypes.CDLL | None = None
_iokit: ctypes.CDLL | None = None


def _frameworks() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    global _cf, _iokit
    if _cf is not None and _iokit is not None:
        return _cf, _iokit

    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")

    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFSetGetCount.argtypes = [ctypes.c_void_p]
    cf.CFSetGetCount.restype = ctypes.c_long
    cf.CFSetGetValues.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    cf.CFSetGetValues.restype = None
    cf.CFGetTypeID.argtypes = [ctypes.c_void_p]
    cf.CFGetTypeID.restype = ctypes.c_ulong
    cf.CFStringGetTypeID.restype = ctypes.c_ulong
    cf.CFNumberGetTypeID.restype = ctypes.c_ulong
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cf.CFRelease.restype = None
    cf.CFRetain.argtypes = [ctypes.c_void_p]
    cf.CFRetain.restype = ctypes.c_void_p

    iokit.IOHIDManagerCreate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    iokit.IOHIDManagerCreate.restype = ctypes.c_void_p
    iokit.IOHIDManagerSetDeviceMatching.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    iokit.IOHIDManagerSetDeviceMatching.restype = None
    iokit.IOHIDManagerCopyDevices.argtypes = [ctypes.c_void_p]
    iokit.IOHIDManagerCopyDevices.restype = ctypes.c_void_p
    iokit.IOHIDDeviceGetProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    iokit.IOHIDDeviceGetProperty.restype = ctypes.c_void_p
    iokit.IOHIDDeviceOpen.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    iokit.IOHIDDeviceOpen.restype = ctypes.c_int32
    iokit.IOHIDDeviceClose.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    iokit.IOHIDDeviceClose.restype = ctypes.c_int32
    iokit.IOHIDDeviceSetReport.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_long,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_long,
    ]
    iokit.IOHIDDeviceSetReport.restype = ctypes.c_int32
    iokit.IOHIDDeviceGetReport.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_long,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_long),
    ]
    iokit.IOHIDDeviceGetReport.restype = ctypes.c_int32

    _cf, _iokit = cf, iokit
    return cf, iokit


def _cfstr(s: str) -> ctypes.c_void_p:
    cf, _ = _frameworks()
    return cf.CFStringCreateWithCString(kCFAllocatorDefault, s.encode("utf-8"), kCFStringEncodingUTF8)


def _get_prop(dev_ref: int, key: str) -> Any:
    cf, iokit = _frameworks()
    k = _cfstr(key)
    try:
        val = iokit.IOHIDDeviceGetProperty(dev_ref, k)
    finally:
        cf.CFRelease(k)
    if not val:
        return None
    t = cf.CFGetTypeID(val)
    if t == cf.CFNumberGetTypeID():
        out = ctypes.c_int64()
        if cf.CFNumberGetValue(val, kCFNumberSInt64Type, ctypes.byref(out)):
            return int(out.value)
        return None
    if t == cf.CFStringGetTypeID():
        buf = ctypes.create_string_buffer(512)
        if cf.CFStringGetCString(val, buf, len(buf), kCFStringEncodingUTF8):
            return buf.value.decode("utf-8", errors="replace")
        return None
    return None


@dataclass
class KeyboardDeviceInfo:
    connection_mode: str  # "wired", "24g", "bluetooth"
    model_label: str
    can_configure: bool
    vid: int
    pid: int
    product: str
    manufacturer: str
    transport: str
    location_id: int
    max_feature_report_size: int
    battery_percent: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["vid_hex"] = f"0x{self.vid:04X}"
        d["pid_hex"] = f"0x{self.pid:04X}"
        return d


def read_bluetooth_keyboard_battery() -> dict[str, Any] | None:
    """
    Read native macOS Bluetooth battery percentage for connected Redragon / K653 / BT keyboards
    via IORegistry (BatteryPercent) and system_profiler SPBluetoothDataType.
    """
    # 1) Fast IORegistry check for any connected non-Apple Bluetooth keyboard with BatteryPercent
    try:
        proc = subprocess.run(
            ["/usr/sbin/ioreg", "-r", "-k", "BatteryPercent", "-l", "-w", "0"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if proc.returncode == 0 and proc.stdout:
            blocks = proc.stdout.split("+-o ")
            for blk in blocks:
                if "BatteryPercent" not in blk:
                    continue
                low = blk.lower()
                if "apple internal" in low or "magic mouse" in low or "trackpad" in low:
                    continue
                if any(
                    tok in low
                    for tok in ("k653", "redragon", "bt3.0 keyboard", "bt5.0", "bt5.1", "bt keyboard", "gaming keyboard", "keyboard")
                ):
                    pct = None
                    prod = "Redragon K653-RGB-PRO"
                    for line in blk.splitlines():
                        if '"BatteryPercent"' in line and "=" in line:
                            try:
                                pct = int(line.split("=", 1)[1].strip())
                            except ValueError:
                                pass
                        elif '"Product"' in line and "=" in line:
                            prod = line.split("=", 1)[1].strip().strip('"')
                    if pct is not None and 0 <= pct <= 100:
                        return {
                            "product": prod,
                            "percent": pct,
                            "charging": False,
                            "source": "bluetooth_ioreg",
                        }
    except Exception:
        pass

    # 2) Fallback: system_profiler SPBluetoothDataType -json
    try:
        proc = subprocess.run(
            ["/usr/sbin/system_profiler", "SPBluetoothDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=3.0,
        )
        if proc.returncode == 0 and proc.stdout:
            data = json.loads(proc.stdout)
            for ctrl in data.get("SPBluetoothDataType", []):
                for item in ctrl.get("device_connected", []) or []:
                    if not isinstance(item, dict):
                        continue
                    for name, props in item.items():
                        if not isinstance(props, dict):
                            continue
                        minor = str(props.get("device_minorType", "")).lower()
                        lname = name.lower()
                        if minor == "keyboard" or any(t in lname for t in ("k653", "redragon", "bt3.0", "bt5.0", "keyboard")):
                            bat_raw = props.get("device_batteryLevelMain") or props.get("device_batteryLevel")
                            if bat_raw is not None:
                                num_str = "".join(ch for ch in str(bat_raw) if ch.isdigit())
                                if num_str:
                                    return {
                                        "product": name,
                                        "percent": max(0, min(100, int(num_str))),
                                        "charging": False,
                                        "source": "bluetooth_sp",
                                    }
    except Exception:
        pass
    return None


def enumerate_k653_devices() -> list[KeyboardDeviceInfo]:
    cf, iokit = _frameworks()
    mgr = iokit.IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone)
    devices: list[KeyboardDeviceInfo] = []
    if mgr:
        try:
            iokit.IOHIDManagerSetDeviceMatching(mgr, None)
            dev_set = iokit.IOHIDManagerCopyDevices(mgr)
            if dev_set:
                try:
                    count = cf.CFSetGetCount(dev_set)
                    if count > 0:
                        arr = (ctypes.c_void_p * count)()
                        cf.CFSetGetValues(dev_set, arr)
                        seen_24g = False
                        for idx in range(count):
                            ref = arr[idx]
                            if not ref:
                                continue
                            vid = int(_get_prop(ref, "VendorID") or 0)
                            pid = int(_get_prop(ref, "ProductID") or 0)
                            mf = int(_get_prop(ref, "MaxFeatureReportSize") or 0)
                            up = int(_get_prop(ref, "PrimaryUsagePage") or 0)
                            u = int(_get_prop(ref, "PrimaryUsage") or 0)

                            if vid == K653_WIRED_VID and pid == K653_WIRED_PID and (mf >= 1000 or (up == 1 and u == 128)):
                                devices.append(
                                    KeyboardDeviceInfo(
                                        connection_mode="wired",
                                        model_label="Redragon K653-RGB-PRO (Cabo USB-C)",
                                        can_configure=True,
                                        vid=vid,
                                        pid=pid,
                                        product=str(_get_prop(ref, "Product") or "Redragon K653-RGB-PRO"),
                                        manufacturer=str(_get_prop(ref, "Manufacturer") or "Redragon"),
                                        transport=str(_get_prop(ref, "Transport") or "USB"),
                                        location_id=int(_get_prop(ref, "LocationID") or 0),
                                        max_feature_report_size=mf,
                                    )
                                )
                            elif vid == K653_24G_VID and pid == K653_24G_PID and not seen_24g:
                                seen_24g = True
                                devices.append(
                                    KeyboardDeviceInfo(
                                        connection_mode="24g",
                                        model_label="Redragon K653-RGB-PRO (Sem Fio 2.4G)",
                                        can_configure=False,
                                        vid=vid,
                                        pid=pid,
                                        product=str(_get_prop(ref, "Product") or "2.4G Wireless Receiver"),
                                        manufacturer=str(_get_prop(ref, "Manufacturer") or "Compx"),
                                        transport=str(_get_prop(ref, "Transport") or "USB"),
                                        location_id=int(_get_prop(ref, "LocationID") or 0),
                                        max_feature_report_size=mf,
                                    )
                                )
                finally:
                    cf.CFRelease(dev_set)
        finally:
            cf.CFRelease(mgr)

    bt = read_bluetooth_keyboard_battery()
    if bt is not None:
        devices.append(
            KeyboardDeviceInfo(
                connection_mode="bluetooth",
                model_label=f"{bt['product']} (Bluetooth)",
                can_configure=False,
                vid=0,
                pid=0,
                product=str(bt["product"]),
                manufacturer="Redragon",
                transport="Bluetooth",
                location_id=0,
                max_feature_report_size=0,
                battery_percent=int(bt["percent"]),
            )
        )

    # Priority: wired (configurable) -> bluetooth (exact battery) -> 2.4g
    prio = {"wired": 0, "bluetooth": 1, "24g": 2}
    devices.sort(key=lambda d: prio.get(d.connection_mode, 9))
    return devices


class K653HidSession:
    """Managed IOKit HID session for the wired Redragon K653-RGB-PRO (0x258A:0x0049)."""

    def __init__(self, location_id: int | None = None):
        self.location_id = location_id
        self._mgr: int = 0
        self._dev_set: int = 0
        self._dev_ref: int = 0

    def __enter__(self) -> "K653HidSession":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        cf, iokit = _frameworks()
        self.close()
        self._mgr = iokit.IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone)
        if not self._mgr:
            raise RuntimeError("IOHIDManagerCreate failed")
        iokit.IOHIDManagerSetDeviceMatching(self._mgr, None)
        self._dev_set = iokit.IOHIDManagerCopyDevices(self._mgr)
        if not self._dev_set:
            self.close()
            raise RuntimeError("No HID devices found")

        count = cf.CFSetGetCount(self._dev_set)
        arr = (ctypes.c_void_p * max(count, 1))()
        if count > 0:
            cf.CFSetGetValues(self._dev_set, arr)

        chosen = 0
        for idx in range(count):
            ref = arr[idx]
            if not ref:
                continue
            vid = int(_get_prop(ref, "VendorID") or 0)
            pid = int(_get_prop(ref, "ProductID") or 0)
            mf = int(_get_prop(ref, "MaxFeatureReportSize") or 0)
            loc = int(_get_prop(ref, "LocationID") or 0)
            if vid == K653_WIRED_VID and pid == K653_WIRED_PID and mf >= 1000:
                if self.location_id is None or loc == self.location_id:
                    chosen = ref
                    break

        if not chosen:
            self.close()
            raise RuntimeError("Teclado Redragon K653-RGB-PRO não encontrado no cabo USB-C.")

        rc = int(iokit.IOHIDDeviceOpen(chosen, kIOHIDOptionsTypeNone))
        if rc != kIOReturnSuccess:
            self.close()
            raise OSError(f"IOHIDDeviceOpen failed: {format_ioreturn(rc)}")

        cf.CFRetain(chosen)
        self._dev_ref = chosen

    def close(self) -> None:
        cf, iokit = _frameworks()
        if self._dev_ref:
            try:
                iokit.IOHIDDeviceClose(self._dev_ref, kIOHIDOptionsTypeNone)
            finally:
                cf.CFRelease(self._dev_ref)
                self._dev_ref = 0
        if self._dev_set:
            cf.CFRelease(self._dev_set)
            self._dev_set = 0
        if self._mgr:
            cf.CFRelease(self._mgr)
            self._mgr = 0

    def set_feature_report(self, report_id: int, data: bytes) -> tuple[bool, int, str]:
        if not self._dev_ref:
            raise RuntimeError("HID session is not open")
        _, iokit = _frameworks()
        payload = bytes(data)
        if not payload or payload[0] != report_id:
            payload = bytes([report_id]) + payload

        last_rc = -1
        for retry in range(3):
            buf = (ctypes.c_uint8 * len(payload))(*payload)
            rc = int(
                iokit.IOHIDDeviceSetReport(
                    self._dev_ref, kIOHIDReportTypeFeature, report_id, buf, len(payload)
                )
            )
            last_rc = rc
            if rc == kIOReturnSuccess:
                return True, rc, format_ioreturn(rc)
            time.sleep(0.05)
        return False, last_rc, format_ioreturn(last_rc)

    def get_feature_report(self, report_id: int, length: int) -> tuple[bool, int, bytes, str]:
        if not self._dev_ref:
            raise RuntimeError("HID session is not open")
        _, iokit = _frameworks()
        last_rc = -1
        last_raw = b""
        for retry in range(3):
            buf = (ctypes.c_uint8 * length)()
            buf[0] = report_id
            rlen = ctypes.c_long(length)
            rc = int(
                iokit.IOHIDDeviceGetReport(
                    self._dev_ref, kIOHIDReportTypeFeature, report_id, buf, ctypes.byref(rlen)
                )
            )
            last_rc = rc
            last_raw = bytes(buf[: max(0, int(rlen.value))])
            if rc == kIOReturnSuccess:
                return True, rc, last_raw, format_ioreturn(rc)
            time.sleep(0.05)
        return False, last_rc, last_raw, format_ioreturn(last_rc)
