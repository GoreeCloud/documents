"""No device required; preflight can issue only approved read-only ADB queries."""
import subprocess
import unittest

from tools.android_device_preflight import PreflightError, check, PACKAGE


class DevicePreflightTest(unittest.TestCase):
    def fixture(self, sdk="36", qemu="0", package="", state="device"):
        commands = []
        responses = {
            ("get-state",): state,
            ("shell", "getprop", "ro.build.version.sdk"): sdk,
            ("shell", "getprop", "ro.kernel.qemu"): qemu,
            ("shell", "pm", "list", "packages", PACKAGE): package,
        }

        def fake_run(argv, **kwargs):
            self.assertEqual(argv[:3], ["adb", "-s", "synthetic-serial:5555"])
            self.assertEqual(kwargs["timeout"], 10)
            self.assertTrue(kwargs["capture_output"])
            self.assertFalse(kwargs["check"])
            key = tuple(argv[3:])
            self.assertIn(key, responses, "No mutating/unknown ADB command allowed")
            commands.append(key)
            return subprocess.CompletedProcess(argv, 0, responses[key], "")

        return fake_run, commands

    def test_physical_uninstalled_device_is_not_claimed_accepted(self):
        runner, commands = self.fixture()
        result = check("synthetic-serial:5555", run=runner)
        self.assertTrue(result["ok"])
        self.assertEqual(result["device_sdk"], 36)
        self.assertEqual(result["device_type"], "physical")
        self.assertFalse(result["documents_package_installed"])
        self.assertFalse(result["apk_installed_by_preflight"])
        self.assertFalse(result["release_accepted"])
        self.assertEqual(len(commands), 4)

    def test_existing_installation_is_reported_without_touching_it(self):
        runner, commands = self.fixture(package="package:" + PACKAGE)
        result = check("synthetic-serial:5555", run=runner)
        self.assertTrue(result["documents_package_installed"])
        self.assertEqual(commands[-1], ("shell", "pm", "list", "packages", PACKAGE))

    def test_emulator_and_old_sdk_are_labeled_not_accepted(self):
        runner, _ = self.fixture(sdk="25", qemu="1")
        result = check("synthetic-serial:5555", run=runner)
        self.assertEqual(result["device_type"], "emulator")
        self.assertFalse(result["ok"])
        self.assertFalse(result["release_accepted"])

    def test_invalid_serial_is_rejected_before_invoking_adb(self):
        for serial in ("", "serial name", "--host", "/tmp/foo", "x" * 129):
            with self.subTest(serial=serial):
                with self.assertRaises(PreflightError):
                    check(serial, run=lambda *_args, **_kw: self.fail("ADB invoked"))

    def test_unavailable_or_ambiguous_device_is_rejected(self):
        runner, _ = self.fixture(state="offline")
        with self.assertRaises(PreflightError):
            check("synthetic-serial:5555", run=runner)
        runner, _ = self.fixture(sdk="unsupported")
        with self.assertRaises(PreflightError):
            check("synthetic-serial:5555", run=runner)
        runner, _ = self.fixture(package="unexpected text")
        with self.assertRaises(PreflightError):
            check("synthetic-serial:5555", run=runner)

    def test_provider_errors_do_not_report_success(self):
        for raised in (OSError("missing adb"), subprocess.TimeoutExpired("adb", 10)):
            def broken(*args, **kwargs):
                raise raised
            with self.assertRaises(PreflightError):
                check("synthetic-serial:5555", run=broken)


if __name__ == "__main__":
    unittest.main()
