"""Android privacy and exported-component source contract.

Protect the declared offline editor boundary without an Android SDK. The
packaged/merged APK manifest is independently checked by Android CI.
"""
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET


ANDROID = "{http://schemas.android.com/apk/res/android}"
MANIFEST = Path(__file__).resolve().parents[1] / "android/app/src/main/AndroidManifest.xml"
COMPONENTS = {"activity", "activity-alias", "service", "receiver", "provider"}


class AndroidPermissionContractTest(unittest.TestCase):
    def test_offline_app_declares_no_privileged_permissions(self):
        root = ET.parse(MANIFEST).getroot()
        self.assertEqual(root.tag, "manifest")
        self.assertEqual(root.findall("uses-permission"), [])
        self.assertEqual(root.findall("uses-permission-sdk-23"), [])
        self.assertEqual(root.findall("uses-permission-sdk-m"), [])
        self.assertEqual(root.findall("permission"), [])
        app = root.find("application")
        self.assertIsNotNone(app)
        self.assertEqual(app.attrib.get(ANDROID + "allowBackup"), "false")
        self.assertNotEqual(app.attrib.get(ANDROID + "usesCleartextTraffic"), "true")
        self.assertNotEqual(app.attrib.get(ANDROID + "debuggable"), "true")

    def test_only_launcher_activity_is_exported(self):
        root = ET.parse(MANIFEST).getroot()
        app = root.find("application")
        components = [(e.tag, e.attrib.get(ANDROID + "name"))
                      for e in app if e.tag in COMPONENTS
                      and e.attrib.get(ANDROID + "exported") == "true"]
        self.assertEqual(components, [("activity", ".MainActivity")])
        launcher = app.find("activity")
        intent = launcher.find("intent-filter")
        actions = {e.attrib.get(ANDROID + "name") for e in intent.findall("action")}
        categories = {e.attrib.get(ANDROID + "name") for e in intent.findall("category")}
        self.assertIn("android.intent.action.MAIN", actions)
        self.assertIn("android.intent.category.LAUNCHER", categories)
        for component in app:
            if component.tag in COMPONENTS and component is not launcher:
                self.assertNotEqual(component.attrib.get(ANDROID + "exported"), "true")

    def test_android_ci_runs_when_permission_tools_or_tests_change(self):
        # This offline/privacy contract is not enough if Android CI silently
        # skips a PR that edits the packaged APK permissions checker itself.
        workflow = MANIFEST.parents[4] / ".github/workflows/android.yml"
        source = workflow.read_text(encoding="utf-8")
        self.assertIn("concurrency:\\n", source)
        triggers = source.split("concurrency:\\n", 1)[0]
        required = {
            "android/**",
            "tools/check_android_permissions.py",
            "tools/android_device_preflight.py",
            "tests/test_android_*.py",
            "tests/test_workflow_action_pins.py",
            ".github/workflows/android.yml",
        }
        for event in ("push", "pull_request"):
            header = "  " + event + ":\\n    paths:\\n"
            self.assertIn(header, triggers)
            section = triggers.split(header, 1)[1].split("\\n  ", 1)[0]
            matched = {
                line.strip().removeprefix('- "').removesuffix('"')
                for line in section.splitlines() if line.strip().startswith('- "')
            }
            self.assertTrue(
                required.issubset(matched),
                f"Android {event} does not cover all security-sensitive paths: {required - matched}"
            )

    def test_unexpected_network_or_storage_access_is_not_silently_allowed(self):
        root = ET.parse(MANIFEST).getroot()
        for child in root:
            if child.tag.startswith("uses-permission"):
                self.fail("Offline editor must explicitly review any new permission")
        app = root.find("application")
        self.assertNotIn(ANDROID + "sharedUserId", root.attrib)
        self.assertEqual(app.attrib[ANDROID + "allowBackup"], "false")


if __name__ == "__main__":
    unittest.main()
