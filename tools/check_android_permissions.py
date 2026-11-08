"""Strict review of permissions in Android SDK aapt dump permissions output.

The offline Documents editor declares no Android platform permissions. AndroidX
may add its own package-scoped dynamic-receiver permission; this exact
declaration/use is the ONLY allowed exception. Run after the APK is built.
"""
import sys

PACKAGE = "com.goreecloud.documents"
INTERNAL = PACKAGE + ".DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"
ALLOWED = {
    "permission: " + INTERNAL,
    "uses-permission: name='" + INTERNAL + "'",
}
MAX_OUTPUT = 32768


class UnexpectedAndroidPermission(ValueError):
    """The packaged APK's offline permission contract was not met."""


def validate_aapt_permissions(source: str) -> dict:
    if not source or len(source) > MAX_OUTPUT:
        raise UnexpectedAndroidPermission("Missing or excessive aapt permission output")
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    if "package: " + PACKAGE not in lines:
        raise UnexpectedAndroidPermission("Unexpected or missing packaged application identity")
    seen = set()
    for line in lines:
        if line.startswith(("uses-permission", "permission:", "permission-group:")):
            if line not in ALLOWED or line in seen:
                raise UnexpectedAndroidPermission(
                    "Unexpected or repeated permission in offline Android APK: " + line
                )
            seen.add(line)
    if ("uses-permission: name='" + INTERNAL + "'" in seen
            and "permission: " + INTERNAL not in seen):
        raise UnexpectedAndroidPermission("Internal permission is used but not declared")
    return {"offline_permission_contract": True, "allowed_internal_lines": len(seen)}


def main():
    try:
        result = validate_aapt_permissions(sys.stdin.read(MAX_OUTPUT + 1))
    except UnexpectedAndroidPermission as failure:
        print("Offline APK permission verification rejected: " + str(failure),
              file=sys.stderr)
        return 1
    print("OFFLINE_APK_PERMISSION_GATE=PASS; reviewed internal lines="
          + str(result["allowed_internal_lines"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
