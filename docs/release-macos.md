# macOS Release Playbook

This playbook creates a teammate-friendly installer artifact for Obscura.

## Goal

Ship a macOS app that non-technical users can install with:

1. Download `.dmg`
2. Drag `Obscura.app` to `Applications`
3. Open app

## One-Time Setup (Maintainer Machine)

1. Install build dependencies:
   - `python -m pip install .[ui,build]`
2. Ensure Tesseract language data exists (`eng` and `spa`):
   - Default lookup: `/opt/homebrew/share/tessdata`
   - Optional repo-local lookup: `assets/tessdata/`

## Build Unsigned Artifacts

```bash
./scripts/package_macos.sh
```

If your machine only has English OCR data, build with:

```bash
OBSCURA_LANGUAGES=eng ./scripts/package_macos.sh
```

Outputs:
- `release/Obscura-<version>-macos-<arch>.zip`
- `release/Obscura-<version>-macos-<arch>.dmg`

## Build Signed + Notarized Artifacts (Recommended)

1. Configure a Developer ID code-sign identity in Keychain.
2. Configure `notarytool` keychain profile.
3. Run:

```bash
export OBSCURA_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export OBSCURA_NOTARY_PROFILE="AC_PASSWORD_PROFILE"
./scripts/package_macos.sh
```

The script will:
- sign `dist/Obscura.app`
- build zip + dmg
- notarize the dmg
- staple notarization ticket
- run Gatekeeper assessment

## Gatekeeper Warning (Unsigned Builds)

Unsigned builds trigger macOS Gatekeeper. Users will see a dialog saying the app
"can't be opened because Apple cannot check it for malicious software."

**First launch workaround (pick one):**

1. **Right-click > Open** -- In Finder, right-click `Obscura.app` and choose
   "Open". Click "Open" in the confirmation dialog. macOS remembers this choice
   for future launches.
2. **Terminal** -- Remove the quarantine attribute:
   ```bash
   xattr -cr /Applications/Obscura.app
   ```

Once either method is used, subsequent launches work normally via double-click.

To eliminate the warning entirely, build with code signing and notarization
(see "Build Signed + Notarized Artifacts" above).

## Publish

1. Create a GitHub Release.
2. Upload the generated `.dmg` (primary installer) and `.zip` (backup).
3. Share only the release link with teammates.
