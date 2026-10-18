#!/bin/zsh
# Runs "/youtube-summarizer <url>" with Claude Code in this folder, then opens
# the report as a PDF in Preview. URL comes from $1, or the clipboard if empty.

set -euo pipefail

# Shortcuts runs scripts with a minimal PATH.
export PATH="$HOME/.local/bin:$HOME/.config/pyenv/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

DIR="${0:A:h}"
REPORTS="$DIR/reports"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
mkdir -p "$REPORTS"

INPUT="${1:-$(pbpaste)}"
INPUT="${INPUT//$'\n'/ }"
if [[ -z "${INPUT// /}" ]]; then
  osascript -e 'display alert "YouTube Summary" message "The clipboard is empty."'
  exit 1
fi

STAMP="$(date +%Y-%m-%d_%H%M%S)"
MD="$REPORTS/summary-$STAMP.md"
HTML="$REPORTS/summary-$STAMP.html"
PDF="$REPORTS/summary-$STAMP.pdf"
LOG="$REPORTS/summary-$STAMP.log"

osascript -e 'display notification "Summarizing video…" with title "YouTube Summary"'

cd "$DIR"
if ! claude -p "/youtube-summarizer $INPUT" \
    --append-system-prompt "You are running non-interactively: never ask questions, pick sensible defaults. Do not save any file. Your final message must contain ONLY the complete Markdown report, with no preamble or closing remarks." \
    --allowedTools "Skill" "Read" "Bash(python3:*)" "Bash(pip:*)" "Bash(pip3:*)" "Bash(echo:*)" \
    --output-format text > "$MD" 2> "$LOG"; then
  osascript -e "display alert \"YouTube Summary failed\" message \"See $LOG\""
  exit 1
fi

# Render Markdown -> HTML (marked.js) -> PDF (headless Chrome).
python3 - "$MD" "$HTML" <<'PY'
import sys, json
md = open(sys.argv[1], encoding="utf-8").read()
html = f"""<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js"></script>
<style>
body {{ font: 11pt -apple-system, "Helvetica Neue", sans-serif; line-height: 1.55; color: #222; max-width: 760px; margin: 0 auto; }}
h1 {{ font-size: 22pt; border-bottom: 2px solid #ddd; padding-bottom: .3em; }}
h2 {{ font-size: 16pt; margin-top: 1.6em; border-bottom: 1px solid #eee; padding-bottom: .2em; }}
h3 {{ font-size: 13pt; }}
code {{ background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }}
pre {{ background: #f4f4f4; padding: 10px; border-radius: 4px; white-space: pre-wrap; }}
blockquote {{ border-left: 3px solid #ccc; margin-left: 0; padding-left: 1em; color: #555; }}
table {{ border-collapse: collapse; }} td, th {{ border: 1px solid #ccc; padding: 4px 8px; }}
</style></head><body><div id="c"></div>
<script>document.getElementById("c").innerHTML = marked.parse({json.dumps(md).replace("</", "<\\/")});</script>
</body></html>"""
open(sys.argv[2], "w", encoding="utf-8").write(html)
PY

"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
  --virtual-time-budget=10000 --print-to-pdf="$PDF" "file://$HTML" >> "$LOG" 2>&1

open -a Preview "$PDF"
