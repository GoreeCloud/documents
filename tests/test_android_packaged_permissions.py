"""Security regressions for the built-APK permission allowlist."""
import unittest

from tools.check_android_permissions import (
    INTERNAL, PACKAGE, UnexpectedAndroidPermission, validate_aapt_permissions,
)


BASE = "package: " + PACKAGE + "\n"
SELF = ("permission: " + INTERNAL + "\n"
        "uses-permission: name='" + INTERNAL + "'\n")


class AndroidPackagedPermissionsTest(unittest.TestCase):
    def test_no_requested_permissions_is_allowed(self):
        result = validate_aapt_permissions(BASE)
        self.assertTrue(result["offline_permission_contract"])
        self.assertEqual(result["allowed_internal_lines"], 0)

    def test_single_declared_androidx_internal_receiver_permission_is_allowed(self):
        result = validate_aapt_permissions(BASE + SELF)
        self.assertEqual(result["allowed_internal_lines"], 2)

    def test_network_storage_and_other_permissions_fail_closed(self):
        attempts = (
            "uses-permission: name='android.permission.INTERNET'",
            "uses-permission: name='android.permission.READ_EXTERNAL_STORAGE'",
            "uses-permission-sdk-23: name='android.permission.CAMERA'",
            "uses-permission: name='com.example.unreviewed'",
            "permission: com.example.unreviewed",
            "permission-group: com.example.unreviewed",
        )
        for permission in attempts:
            with self.subTest(permission=permission):
                with self.assertRaises(UnexpectedAndroidPermission):
                    validate_aapt_permissions(BASE + SELF + permission + "\n")

    def test_mismatch_repetition_and_undeclared_use_fail_closed(self):
        for output in (
            "package: com.other.app\n" + SELF,
            BASE + "uses-permission: name='" + INTERNAL + "'\n",
            BASE + SELF + "uses-permission: name='" + INTERNAL + "'\n",
            BASE + "permission: " + INTERNAL + "\npermission: " + INTERNAL + "\n",
            "",
            BASE + " " * 32768,
        ):
            with self.subTest(first=output[:48]):
                with self.assertRaises(UnexpectedAndroidPermission):
                    validate_aapt_permissions(output)


if __name__ == "__main__":
    unittest.main()
