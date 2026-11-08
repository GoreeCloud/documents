"""Fail-closed, read-only Android device preflight for Documents previews.

No APK installation, ADB pairing, shell mutation, credential access or file
transfer. An explicitly selected existing ADB serial is always required.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess


PACKAGE = "com.goreecloud.documents"
MIN_SDK = 26
SERIAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class PreflightError(ValueError):
    """Cannot safely validate the explicitly selected device."""


def check(serial: str, run=None) -> dict:
    if not SERIAL.fullmatch(serial):
        raise PreflightError("Invalid explicit ADB serial")
    if run is None:
        run = subprocess.run

    def readonly(*args: str) -> str:
        command = ["adb", "-s", serial, *args]
        try:
            result = run(command, capture_output=True, text=True,
                         timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise PreflightError("ADB read-only query unavailable or timed out") from None
        if result.returncode != 0:
            raise PreflightError("ADB read-only query rejected") from None
        if len(result.stdout) > 4096:
            raise PreflightError("Unexpectedly large ADB response")
        return result.stdout.strip()

    if readonly("get-state") != "device":
        raise PreflightError("Selected ADB target is not ready")
    version = readonly("shell", "getprop", "ro.build.version.sdk")
    if not version.isascii() or not version.isdecimal():
        raise PreflightError("Invalid Android SDK version response")
    sdk = int(version)
    if not 1 <= sdk <= 999:
        raise PreflightError("Invalid Android SDK version response")
    is_emulator = readonly("shell", "getprop", "ro.kernel.qemu")
    if is_emulator not in ("", "0", "1"):
        raise PreflightError("Unexpected emulator classification")
    installed = readonly("shell", "pm", "path", PACKAGE)
    if installed and not all(
        line.startswith("package:/") and "\n" not in line
        for line in installed.splitlines()
    ):
        raise PreflightError("Unexpected installed-package response")
    return {
        "ok": sdk >= MIN_SDK,
        "min_sdk": MIN_SDK,
        "device_sdk": sdk,
        "device_type": "emulator" if is_emulator == "1" else (
            "physical_or_unknown" if is_emulator == "" else "physical"
        ),
        "documents_package_installed": bool(installed),
        "apk_installed_by_preflight": False,
        "release_accepted": False,
        "note": "Read-only preflight; signing, installation, data integrity and rollback are separate gates",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Explicit existing ADB device serial")
    args = parser.parse_args(argv)
    try:
        output = check(args.serial)
    except PreflightError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "release_accepted": False}))
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
