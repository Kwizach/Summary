#!/bin/zsh
# Runs "/youtube-summarizer <url>" with Claude Code in this folder, renders the
# report as an HTML page with the video embedded, and opens it in the browser.
# URL comes from $1, or the clipboard if empty.

set -euo pipefail

# Shortcuts runs scripts with a minimal PATH.
export PATH="$HOME/.local/bin:$HOME/.config/pyenv/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

DIR="${0:A:h}"
REPORTS="$DIR/reports"
PORT="${YT_SUMMARY_PORT:-47821}"
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

python3 "$DIR/render_report.py" "$MD" "$HTML" "$INPUT" 2>> "$LOG"

# YouTube embeds don't play from file:// pages, so serve reports/ on localhost.
# The server is started once and keeps running in the background.
touch "$REPORTS/.yt-summary-server"
if ! curl -sf "http://127.0.0.1:$PORT/.yt-summary-server" > /dev/null; then
  nohup python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$REPORTS" > /dev/null 2>&1 &!
  for _ in {1..20}; do
    curl -sf "http://127.0.0.1:$PORT/.yt-summary-server" > /dev/null && break
    sleep 0.25
  done
fi

open "http://localhost:$PORT/${HTML:t}"
