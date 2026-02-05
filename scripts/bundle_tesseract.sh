#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./scripts/bundle_tesseract.sh [out_dir] [languages]

Bundles Tesseract language files into a local folder for packaging.

Arguments:
  out_dir    Output directory (default: assets/tessdata)
  languages  '+'-joined language codes (default: eng+spa)

Examples:
  ./scripts/bundle_tesseract.sh
  ./scripts/bundle_tesseract.sh assets/tessdata eng
  ./scripts/bundle_tesseract.sh assets/tessdata eng+spa
EOF
  exit 0
fi

out_dir=${1:-"assets/tessdata"}
languages=${2:-"eng+spa"}

IFS='+' read -r -a lang_array <<<"$languages"

find_tessdata() {
  local candidates=(
    "assets/tessdata"
    "/opt/homebrew/share/tessdata"
    "/usr/local/share/tessdata"
    "/usr/share/tesseract-ocr/5/tessdata"
  )

  for candidate in "${candidates[@]}"; do
    [[ -d "$candidate" ]] || continue
    local all_present=1
    for lang in "${lang_array[@]}"; do
      [[ -f "$candidate/${lang}.traineddata" ]] || { all_present=0; break; }
    done
    if [[ "$all_present" -eq 1 ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

tessdata=$(find_tessdata || true)
if [[ -z "${tessdata}" ]]; then
  echo "Tesseract language data not found for: ${languages}" >&2
  echo "Install via Homebrew (for all requested languages), or place files in assets/tessdata." >&2
  exit 1
fi

mkdir -p "$out_dir"
for lang in "${lang_array[@]}"; do
  cp "$tessdata/${lang}.traineddata" "$out_dir/"
done

echo "Bundled tessdata languages (${languages}) to: $out_dir"
