#!/usr/bin/env bash
#
# markdown-to-pdf.sh — Convert a Markdown file to PDF via pandoc + headless Chrome.
#
# Renders wide tables in landscape orientation with a compact, print-friendly
# stylesheet (fixed table layout, word-wrapping, keep-together blocks via a
# `.keep-together` CSS class you can wrap around a section in raw HTML if
# needed). Relative image paths (e.g. ![diagram](diagram.svg)) resolve
# relative to the Markdown file's own directory.
#
# Requirements:
#   - pandoc (https://pandoc.org)
#   - Google Chrome or Chromium (used headless for the actual PDF rendering,
#     since pandoc alone needs a LaTeX engine or wkhtmltopdf to emit PDF)
#
# Usage:
#   markdown-to-pdf.sh <input.md> [output.pdf]
#
# Examples:
#   utils/scripts/markdown/markdown-to-pdf.sh docs/ORBIT_CAPABILITY_MATRIX.md
#   utils/scripts/markdown/markdown-to-pdf.sh docs/ORBIT_CAPABILITY_MATRIX.md /tmp/matrix.pdf

set -euo pipefail

usage() {
  echo "Usage: $(basename "$0") <input.md> [output.pdf]" >&2
  exit 1
}

[ "$#" -ge 1 ] || usage

INPUT_MD="$1"
[ -f "$INPUT_MD" ] || { echo "Error: input file not found: $INPUT_MD" >&2; exit 1; }

if [ "$#" -ge 2 ]; then
  OUTPUT_PDF="$2"
else
  OUTPUT_PDF="${INPUT_MD%.md}.pdf"
fi

command -v pandoc >/dev/null 2>&1 || {
  echo "Error: pandoc is required. Install it from https://pandoc.org/installing.html" >&2
  exit 1
}

# Locate a Chrome/Chromium binary across macOS and Linux.
find_chrome() {
  local candidates=(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Chromium.app/Contents/MacOS/Chromium"
    "google-chrome"
    "google-chrome-stable"
    "chromium"
    "chromium-browser"
  )
  for c in "${candidates[@]}"; do
    if [ -x "$c" ]; then
      echo "$c"
      return 0
    fi
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

CHROME_BIN="$(find_chrome)" || {
  echo "Error: could not find Google Chrome or Chromium. Install one, or set CHROME_BIN to its path." >&2
  exit 1
}
: "${CHROME_BIN:=${CHROME_BIN}}"
if [ -n "${CHROME_BIN_OVERRIDE:-}" ]; then
  CHROME_BIN="$CHROME_BIN_OVERRIDE"
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

STYLE_FILE="$WORKDIR/style.html"
cat > "$STYLE_FILE" << 'EOF'
<style>
@page { size: A4 landscape; margin: 14mm 10mm; }
body { font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 0 auto; line-height: 1.45; color: #1a1a1a; }
h1,h2,h3 { border-bottom: 1px solid #ddd; padding-bottom: 6px; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 0.72em; table-layout: fixed; }
th, td { border: 1px solid #ccc; padding: 5px 7px; text-align: left; vertical-align: top; word-wrap: break-word; overflow-wrap: break-word; }
th { background: #f0f0f0; }
code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px; word-break: break-word; }
pre { background: #f4f4f4; padding: 10px; overflow-x: auto; }
blockquote { border-left: 4px solid #ccc; margin-left: 0; padding-left: 12px; color: #444; }
img { max-width: 100%; }
.keep-together { page-break-inside: avoid; break-inside: avoid; }
@media print { body { margin: 0; max-width: 100%; } }
</style>
EOF

HTML_FILE="$WORKDIR/rendered.html"
INPUT_DIR="$(cd "$(dirname "$INPUT_MD")" && pwd)"

pandoc "$INPUT_MD" \
  -f gfm -t html5 -s \
  -H "$STYLE_FILE" \
  -o "$HTML_FILE" \
  --embed-resources --standalone \
  --resource-path="$INPUT_DIR"

"$CHROME_BIN" \
  --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$OUTPUT_PDF" \
  "$HTML_FILE" >/dev/null 2>&1 || true

if [ -f "$OUTPUT_PDF" ]; then
  echo "Wrote $OUTPUT_PDF"
else
  echo "Error: PDF was not produced. Re-run without redirecting stderr to debug." >&2
  exit 1
fi
