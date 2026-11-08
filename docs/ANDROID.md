# GoreeCloud Documents — Android offline editor preview

**Status:** Native Android offline editor development-preview source is integrated into `main`. Android 35 emulator and debug/JVM CI have passed, including a host-driven force-stop test. No standalone APK has been delivered or installed on an owner's device; physical-device, signing, distribution and Stable acceptance remain open.

## Purpose and boundaries

This is a native Kotlin/Jetpack Compose Android client that **opens and edits local files using Android's Storage Access Framework (SAF)**. It is not a WebView, browser shortcut or wrapper.

The Android preview deliberately requests **no INTERNET or broad storage permissions**. It does not connect to the private Documents API, automatically sync files, or access the GoreeCloud Drive documentation authority.

## Implemented source

- A native on-device library homepage that reloads app-private saved records at startup, with searchable document cards, grid/list preference and a file-format badge in the upper-right of every thumbnail.
- Create a new GoreeCloud document, open existing `.gcdoc` or plain UTF-8 `.md` using the Android system document picker, and edit the title, logical folder and Markdown source.
- **Save** edits to the app-private atomic document record; separately **Export** an explicit copy through Android's **CreateDocument** picker. Export does not mark local unsaved edits as saved or silently overwrite the original imported file.
- Unsaved-edit confirmation on library navigation and Android Back, plus a manual discard action; newer edits made during background Save remain marked unsaved.
- A strict, bounded `.gcdoc` v1 JSON decoder and encoder with schema, UTF-8, document-size, and folder validation aligned to the backend format.
- Native light/dark color schemes using GC UI's verified Iris palette role references.

**Caution:** The private library now stores document records locally, and Android 35 hosted emulator instrumentation has verified Activity recreation and reopening a saved record; **a host-driven force-stop and relaunch passed on a disposable Android 35 emulator; physical-device process death, reboot, low-storage and provider-failure recovery are not yet accepted**. A new blank document is persisted when created; later edits are durable only after an explicit successful **Save**. Unsaved edits can be lost on forced termination. App-private files are normally removed on uninstall, and Android backup is disabled. A SAF Export is an independent copy that may fail or be cancelled; verify it externally. The preview does not provide encrypted off-device backup, atomic writes to third-party document providers, or cloud sync.

## App-private storage component — connected in source, awaiting device acceptance

The branch includes `android/app/src/main/java/com/goreecloud/documents/DocumentShelf.kt`, a native app-private, atomic-file document store. Its Robolectric regression tests cover reopening, updating, invalid identifiers, malformed and oversized entries. `MainActivity.kt` now loads shelf records on startup, persists newly created and imported documents, and saves edited records on a background thread. Export is a separate SAF operation that does not update the private save snapshot. CI run [42012234517](https://github.com/GoreeCloud/documents/actions/runs/42012234517) passed JVM tests and `assembleDebug` at exact code head `a3dd1be535f2d68be2fbc450e563099d9e4ebf38`.

**Verification boundary:** CI proves Kotlin compilation, codec/shelf unit tests and a debug build, not full interactive behavior on physical Android. The host-driven emulator force-stop/relaunch exercise now covers previously committed synthetic data, but further Android-device tests are required for unsaved edits across real termination/reboot, edit → Save → relaunch and external-provider scenarios; verify dirty-state retention during concurrent edits, SAF cancellation, read/write failures, storage exhaustion, app-background behavior, accessibility and corruption recovery. Do not declare production durability or distribute an APK without those checks.

## Corrupted local-record handling

The app-private `DocumentShelf` now reuses the strict UTF-8 decoder from
`DocumentCodec` when inspecting local JSON records. Malformed byte sequences
are rejected instead of silently being replaced by the Unicode replacement
character, which could alter saved text without permission. The scan preserves
unreadable source files and reports their count; it does not automatically
erase or rewrite damaged documents. Robolectric coverage includes invalid
UTF-8 and preservation of the original bytes.

The strict decoder is now invoked by the Android UI's saved-document loading
path through `DocumentShelf.scan()`. A green unit test still does not establish
full app lifecycle durability or recovery behavior on a physical device.

## Host-driven emulator force-stop and relaunch — verified source preview

I require an explicit Save to survive process termination without falsely
claiming that unsaved edits are durable. On November 7, 2026 the Android
35 GitHub Actions emulator ran `ProcessDeathDurabilityTest` in **two
separate instrumentation invocations**: one saved a unique synthetic
record; the host started the Activity, ran `adb shell am force-stop`,
checked the app process had exited, restarted the Activity, and ran a
second instrumentation that read and verified the original committed
record and removed only its own synthetic fixture.

[Android CI run 42434441252](https://github.com/GoreeCloud/documents/actions/runs/42434441252)
passed both `android-debug` and `android-emulator` at source head
`d8ca098f161ea774cc4c464c44683fffe56d83f6`, including this
two-phase test. The ordinary instrumentation suite skips this fixture
unless the host supplies its explicit phase; CI runs both phases
separately. This demonstrates an actual **emulator force-stop** path,
not a physical-device power failure, spontaneous process crash, reboot,
storage exhaustion, external-provider partial write, APK distribution
or Stable release. The Android application was not installed on an
owner's physical phone during this validation.

## Legacy backup discovery (source preview)

The app-private shelf now discovers a valid legacy `.json.bak` sidecar even when its base `.json` file is missing. The matching `android.util.AtomicFile.openRead()` performs recovery using Android's platform behavior rather than treating the backup as an unrelated document. Discovery deduplicates base/backup entries and rejects symbolic links before reading them. Focused Robolectric fixtures cover orphaned committed data, malformed backup preservation, and symlink rejection. This is a source-level regression improvement; exact-head CI and true device process-death/storage-failure acceptance are tracked separately. The shelf does not provide cloud or off-device backup.

## Shared native-format interoperability fixture

The same public, non-sensitive reference file,
`android/app/src/test/resources/fixtures/reference-v1.gcdoc`, is parsed by both
the Python storage/import test and the Android/JVM codec test. It exercises a
v1 native document, UTF-8 Unicode, Markdown line breaks, logical folder paths
and re-export equivalence. This fixture provides a specific, reproducible
cross-platform contract; it is not a substitute for all possible property,
corruption or future-version compatibility tests.

## Toolchain

The development project is located under `android/`. It currently uses the known GoreeCloud Tasks Android baseline: Android Gradle Plugin 8.8.2, Kotlin/Compose compiler 2.0.21, Compose BOM 2025.02.00, Java 17 and Android SDK 35. These versions are a project development baseline, not an assertion that all dependencies are at the latest supported release.

A development machine with an authorized Android SDK and Gradle 8.10.2 can check:

```sh
gradle -p android :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

The repository's Android CI workflow performs the same checks. **A green compile is not equivalent to device testing or APK delivery.**

## Android APK integrity and signature preflight

Before any APK is considered for installation, I require a verified
package identity, content integrity and an appropriate signing and
custody plan. The development CI now contains a **fail-closed debug APK
preflight** using the reviewed GoreeCloud Android Toolkit source
pinned to `70655c1c210984bc72a4a93436eaf8a6e3c59d8b`.

The checks audit public tracked files for sensitive artifacts, verify
bounded APK ZIP structure and SHA-256, invoke Android SDK
`apksigner verify`, and confirm the compiled application package is
`com.goreecloud.documents` via `aapt dump badging`. The Toolkit
inspector distinguishes ZIP integrity from signature, identity and
device verification. This additional CI step is **development source
only** until its exact-head hosted run passes.

A valid **debug** signature is not a trusted release signature.
CI does not export, upload, install on an owner's device, or deliver the
APK. Release signing-key custody, official hash/provenance, standalone
APK storage in GoreeCloud/Artifacts, installation and upgrade/rollback
remain separate acceptance gates.

## Explicit-device, read-only ADB preflight

Before any physical Android installation, I require an explicitly selected
target and a defensible statement of what was *actually* inspected. The
development utility `tools/android_device_preflight.py` never installs,
removes, launches, stops, pairs or modifies an app/device. It requires the
exact ADB serial supplied with `--serial`; rejecting missing, malformed
or option-like values avoids accidentally selecting the connected TV
instead of the intended phone.

From a reviewed local checkout with Android SDK platform-tools in PATH:

```sh
python3 tools/android_device_preflight.py --serial 'EXPLICIT_ADB_SERIAL'
```

Only four read-only ADB queries are permitted: device readiness, Android API
level, emulator classification, and an exact installed-package listing for
`com.goreecloud.documents` (without probing its private APK path). The utility refuses unexpected responses,
transport failures and old Android API levels (minimum 26), and outputs
machine-readable JSON with `release_accepted: false`. It never requests
an APK path or an install command. All failure cases are testable with
synthetic subprocess fixtures before interacting with a device.

A successful read-only preflight is **not** physical runtime acceptance,
consent to install, an APK signature check, a privacy audit or release
approval. The separate standing GoreeCloud/Artifacts standalone APK
delivery requirement and all app install/update/rollback gates still apply.

## Fail-closed offline permission contract

The app's declared privacy boundary is **no network or broad-storage permissions**, Android backup disabled, and only the launcher Activity exported. Source tests in `tests/test_android_permission_contract.py` check the declared Android manifest, exported components and backup/cleartext settings. The Android APK build workflow additionally checks the merged **packaged** manifest through Android SDK `aapt`, rejects any network, broad-storage or other unexpected permission, and enforces minimum SDK 26 and target SDK 35. AndroidX currently merges one app-defined `com.goreecloud.documents.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` declaration and its matching use, which is explicitly allowed by `tools/check_android_permissions.py`; unknown, duplicate or undeclared permission uses fail closed. This app-scoped receiver permission is not an Android platform network or storage grant. These are development source/privacy checks; the corrected exact-head CI must pass before accepting the workflow change. They do not substitute for runtime traffic monitoring, an independent privacy review or physical-device approval.

## Android delivery and release gate

Per GoreeCloud governance, every APK offered for installation/testing must be a **standalone `.apk` verified in the canonical Google Drive `GoreeCloud/Artifacts` directory**. GitHub Actions build output or ZIP archives are not a compliant APK delivery. No APK should be described as provided until that location, file identity, checksum and relevant build provenance are verified.

Before distribution, test file picker provider edge cases, document persistence through activity recreation, keyboard/accessibility and dynamic type, light/dark modes, OS permissions, formatting fidelity, retention and recovery, APK signing and rollback, and actual device installation. Proper single-backend synchronization with GoreeCloud Identity and Mesh is future work.
