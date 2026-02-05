"""Build a distributable macOS Obscura.app with PyInstaller."""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))
from obscura.runtime import SYSTEM_TESSDATA_DIRS

APP_NAME = "Obscura"
ENTRYPOINT = pathlib.Path("src/obscura/__main__.py")
UI_DIR = pathlib.Path("src/obscura/ui")
DEFAULT_LANGUAGES = ("eng", "spa")


def _die(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _find_tessdata(languages: tuple[str, ...]) -> pathlib.Path:
    custom = pathlib.Path("assets/tessdata")
    candidates = [custom, *SYSTEM_TESSDATA_DIRS]
    for candidate in candidates:
        if not candidate.exists():
            continue
        if all((candidate / f"{lang}.traineddata").exists() for lang in languages):
            return candidate
    missing = ", ".join(f"{lang}.traineddata" for lang in languages)
    _die(
        "Tesseract language data not found. "
        f"Expected files: {missing}. "
        "Install tesseract language data (e.g. `brew install tesseract`) "
        "or place files in assets/tessdata/."
    )


def _pyinstaller_installed() -> bool:
    check = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        capture_output=True,
        text=True,
    )
    return check.returncode == 0


def _build_cmd(tessdata_dir: pathlib.Path, languages: tuple[str, ...]) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--paths",
        "src",
        "--add-data",
        f"{UI_DIR}:obscura/ui",
        "--collect-all",
        "pymupdf",
        "--collect-all",
        "webview",
        "--hidden-import",
        "regex",
        "--hidden-import",
        "obscura",
        str(ENTRYPOINT),
    ]
    for lang in languages:
        cmd.extend(
            [
                "--add-data",
                f"{tessdata_dir / f'{lang}.traineddata'}:obscura/tessdata",
            ]
        )
    return cmd


def build(languages: tuple[str, ...]) -> pathlib.Path:
    if sys.platform != "darwin":
        _die("macOS builds only. Run packaging on macOS.")
    if not _pyinstaller_installed():
        _die(
            "PyInstaller is not installed in this environment. "
            "Install with `python -m pip install .[ui,build]`."
        )
    if not ENTRYPOINT.exists():
        _die(f"Entrypoint not found: {ENTRYPOINT}")
    if not UI_DIR.exists():
        _die(f"UI directory not found: {UI_DIR}")

    tessdata_dir = _find_tessdata(languages)
    cmd = _build_cmd(tessdata_dir=tessdata_dir, languages=languages)
    subprocess.run(cmd, check=True)

    app_path = pathlib.Path("dist") / f"{APP_NAME}.app"
    if not app_path.exists():
        _die(f"Build finished but app not found: {app_path}")

    print(f"Build complete: {app_path}")
    print(f"Bundled tessdata from: {tessdata_dir}")
    return app_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Obscura.app for macOS.")
    parser.add_argument(
        "--languages",
        default="+".join(DEFAULT_LANGUAGES),
        help="Tesseract language codes to bundle, joined by '+'. Default: eng+spa",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    languages = tuple(part.strip() for part in args.languages.split("+") if part.strip())
    if not languages:
        _die("At least one language code is required.")
    build(languages=languages)


if __name__ == "__main__":
    main()
