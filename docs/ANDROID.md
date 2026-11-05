# GoreeCloud Documents — Android offline editor preview

**Status:** Source-only development branch. No verified APK has been delivered. Android runtime, permissions, visual quality, installation, upgrades and accessibility are not yet accepted.

## Purpose and boundaries

This is a native Kotlin/Jetpack Compose Android client that **opens and edits local files using Android's Storage Access Framework (SAF)**. It is not a WebView, browser shortcut or wrapper.

The Android preview deliberately requests **no INTERNET or broad storage permissions**. It does not connect to the private Documents API, automatically sync files, or access the GoreeCloud Drive documentation authority.

## Implemented source

- A local session homepage with searchable document cards, grid/list preference and a clear file-format badge in the upper-right of every thumbnail.
- Create a new GoreeCloud document, open existing `.gcdoc` or plain UTF-8 `.md` using the Android system document picker, and edit the title, logical folder and Markdown source.
- Export the current document through Android's **CreateDocument** picker. Saving uses an explicitly selected destination; it does not silently overwrite the original input.
- Unsaved-edit confirmation when leaving the editor, plus a manual discard action.
- A strict, bounded `.gcdoc` v1 JSON decoder and encoder with schema, UTF-8, document-size, and folder validation aligned to the backend format.
- Native light/dark color schemes using GC UI's verified Iris palette role references.

**Caution:** Session document cards exist only in memory and can disappear when the application is terminated or recreated. The grid/list **preference only** persists in app preferences. A new document is **not durable until exported to a file**. Saving to SAF may fail if the selected document provider cannot write or runs out of space; verify the saved file externally. The preview does not perform atomic external-provider writes or encrypted off-device backups.

## App-private storage component — implemented, not wired

The draft branch now also contains `android/app/src/main/java/com/goreecloud/documents/DocumentShelf.kt`, a native app-private, atomic-file document store. Its own regression tests cover file reopening, updating records, invalid identifiers, malformed entries and oversized content. The Android workflow passed at exact branch head `eea502741be35ad3572fa23f0aee898d4aae66df`, including `testDebugUnitTest` and `assembleDebug`.

**This component is not yet connected to `MainActivity.kt`**: the current on-screen document list still exists only for the session. The attempted UI integration change was blocked by platform safety checks. Do not infer persistent UI behavior or successful recovery on an Android device from the storage-component unit tests. Required follow-up: review and authorize a complete data-flow integration; verify Save and Export remain distinct and that unsaved drafts are not silently discarded; run UI lifecycle and interruption tests before describing the native Android library as durable.

## Toolchain

The development project is located under `android/`. It currently uses the known GoreeCloud Tasks Android baseline: Android Gradle Plugin 8.8.2, Kotlin/Compose compiler 2.0.21, Compose BOM 2025.02.00, Java 17 and Android SDK 35. These versions are a project development baseline, not an assertion that all dependencies are at the latest supported release.

A development machine with an authorized Android SDK and Gradle 8.10.2 can check:

```sh
gradle -p android :app:testDebugUnitTest :app:assembleDebug --no-daemon
```

The repository's Android CI workflow performs the same checks. **A green compile is not equivalent to device testing or APK delivery.**

## Android delivery and release gate

Per GoreeCloud governance, every APK offered for installation/testing must be a **standalone `.apk` verified in the canonical Google Drive `GoreeCloud/Artifacts` directory**. GitHub Actions build output or ZIP archives are not a compliant APK delivery. No APK should be described as provided until that location, file identity, checksum and relevant build provenance are verified.

Before distribution, test file picker provider edge cases, document persistence through activity recreation, keyboard/accessibility and dynamic type, light/dark modes, OS permissions, formatting fidelity, retention and recovery, APK signing and rollback, and actual device installation. Proper single-backend synchronization with GoreeCloud Identity and Mesh is future work.
