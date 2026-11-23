#!/usr/bin/env python3
"""
Build the native macOS Redragon K653 Control.app bundle and install it to
/Applications/Redragon K653 Control.app.
"""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "Redragon K653 Control.app"
LOCAL_APP = ROOT / APP_NAME
SYSTEM_APP = Path("/Applications") / APP_NAME
SWIFT_SRC = ROOT / "macos_app.swift"
ICON_SRC = ROOT / "assets" / "keyimg.png"

ICONSET_SPECS = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


def build_icns(dest_icns: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        master_png = tmp_dir / "master_1024.png"
        renderer = tmp_dir / "render_icon.swift"
        renderer.write_text(
            """
import Cocoa

let srcPath = CommandLine.arguments[1]
let outPath = CommandLine.arguments[2]
let size = NSSize(width: 1024, height: 1024)

guard let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: 1024, pixelsHigh: 1024,
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
) else { fatalError("Bitmap error") }

NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)

let rect = NSRect(x: 84, y: 84, width: 856, height: 856)
let squircle = NSBezierPath(roundedRect: rect, xRadius: 196, yRadius: 196)
squircle.addClip()

let bgGrad = NSGradient(
    starting: NSColor(calibratedRed: 0.055, green: 0.067, blue: 0.098, alpha: 1.0),
    ending: NSColor(calibratedRed: 0.125, green: 0.080, blue: 0.110, alpha: 1.0)
)
bgGrad?.draw(in: rect, angle: 90)

if let redGlow = NSGradient(
    starting: NSColor(calibratedRed: 1.0, green: 0.12, blue: 0.24, alpha: 0.36),
    ending: NSColor.clear
) {
    redGlow.draw(in: rect, relativeCenterPosition: NSPoint(x: 0.0, y: 0.35))
}

if let kbImg = NSImage(contentsOfFile: srcPath) {
    let imgSize = kbImg.size
    let targetW: CGFloat = 760
    let targetH = targetW * (imgSize.height / max(1, imgSize.width))
    let drawRect = NSRect(
        x: (size.width - targetW) / 2.0,
        y: (size.height - targetH) / 2.0 - 20,
        width: targetW,
        height: targetH
    )
    kbImg.draw(in: drawRect, from: .zero, operation: .sourceOver, fraction: 1.0)
}

let attrs: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 82, weight: .heavy),
    .foregroundColor: NSColor(calibratedRed: 1.0, green: 0.28, blue: 0.38, alpha: 1.0),
]
let title = NSString(string: "K653 PRO")
let tsize = title.size(withAttributes: attrs)
title.draw(at: NSPoint(x: (size.width - tsize.width) / 2.0, y: 690), withAttributes: attrs)

NSColor(calibratedWhite: 1.0, alpha: 0.16).setStroke()
squircle.lineWidth = 6
squircle.stroke()
NSGraphicsContext.restoreGraphicsState()

if let data = rep.representation(using: .png, properties: [:]) {
    try data.write(to: URL(fileURLWithPath: outPath))
}
""",
            encoding="utf-8",
        )
        _run(["/usr/bin/swift", str(renderer), str(ICON_SRC), str(master_png)])
        iconset = tmp_dir / "AppIcon.iconset"
        iconset.mkdir()
        for filename, px in ICONSET_SPECS:
            _run(["/usr/bin/sips", "-z", str(px), str(px), str(master_png), "--out", str(iconset / filename)])
        dest_icns.parent.mkdir(parents=True, exist_ok=True)
        _run(["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", str(dest_icns)])


def build_bundle() -> None:
    if LOCAL_APP.exists():
        shutil.rmtree(LOCAL_APP)

    contents = LOCAL_APP / "Contents"
    macos_dir = contents / "MacOS"
    res_dir = contents / "Resources"
    backend_dir = res_dir / "backend"
    macos_dir.mkdir(parents=True, exist_ok=True)
    backend_dir.mkdir(parents=True, exist_ok=True)

    binary = macos_dir / "RedragonK653Control"
    _run(
        [
            "/usr/bin/swiftc",
            "-O",
            "-framework",
            "Cocoa",
            "-framework",
            "WebKit",
            str(SWIFT_SRC),
            "-o",
            str(binary),
        ]
    )

    build_icns(res_dir / "AppIcon.icns")

    for fname in ("hid_bridge.py", "device_manager.py", "server.py"):
        shutil.copy2(ROOT / fname, backend_dir / fname)
    shutil.copytree(ROOT / "protocols", backend_dir / "protocols")
    shutil.copytree(ROOT / "ui", backend_dir / "ui")
    shutil.copytree(ROOT / "assets", backend_dir / "assets")

    info = {
        "CFBundleName": "Redragon K653 Control",
        "CFBundleDisplayName": "Redragon K653 Control",
        "CFBundleIdentifier": "com.local.redragon.k653.control",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleExecutable": "RedragonK653Control",
        "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as fp:
        plistlib.dump(info, fp)

    if SYSTEM_APP.exists():
        shutil.rmtree(SYSTEM_APP)
    shutil.copytree(LOCAL_APP, SYSTEM_APP)
    print(f"Built local bundle : {LOCAL_APP}")
    print(f"Installed system app: {SYSTEM_APP}")


if __name__ == "__main__":
    build_bundle()
