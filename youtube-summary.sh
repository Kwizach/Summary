#!/bin/zsh
# Summarize a YouTube video with Claude Code ("/youtube-summarizer <url>") and
# show the report as a web page with the video embedded.
#
#   youtube-summary.sh [URL]            run every step (URL defaults to the clipboard)
#
# The Shortcut runs the steps one by one, so its progress meter moves:
#   youtube-summary.sh start [URL]      check link, open live progress page, print JOB
#   youtube-summary.sh transcript JOB   fetch the transcript
#   youtube-summary.sh summarize JOB    have Claude write the report
#   youtube-summary.sh finish JOB       build the final page
#
# Each step prints JOB so the next Shortcut action can receive it.
# Files: reports/JOB.md, reports/JOB.html, and reports/.jobs/JOB/ (status, transcript, logs).

set -euo pipefail
setopt extendedglob

# Shortcuts runs scripts with a minimal PATH.
export PATH="$HOME/.local/bin:$HOME/.config/pyenv/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

DIR="${0:A:h}"
REPORTS="$DIR/reports"
PORT="${YT_SUMMARY_PORT:-47821}"
EXTRACT="$DIR/.claude/skills/youtube-summarizer/scripts/extract-transcript.py"

status() { python3 "$DIR/job_status.py" set "$JOBDIR/status.json" "$@"; }

fail() {  # fail STEP MESSAGE
  local message="${2#❌ }"
  status error "$message" "failed_step=$1"
  print -u2 "❌ $message"
  exit 1
}

set_job() {
  JOB="${1//[[:space:]]/}"
  JOBDIR="$REPORTS/.jobs/$JOB"
  [[ -n "$JOB" && -d "$JOBDIR" ]] || { print -u2 "❌ Unknown job: '$1'"; exit 1; }
  URL="$(python3 "$DIR/job_status.py" get "$JOBDIR/status.json" url)"
}

# YouTube embeds don't play from file:// pages, so serve reports/ on localhost.
# The server is started once and keeps running in the background.
ensure_server() {
  touch "$REPORTS/.yt-summary-server"
  curl -sf "http://127.0.0.1:$PORT/.yt-summary-server" > /dev/null && return
  nohup python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$REPORTS" > /dev/null 2>&1 &!
  for _ in {1..20}; do
    curl -sf "http://127.0.0.1:$PORT/.yt-summary-server" > /dev/null && return
    sleep 0.25
  done
}

step_start() {
  local input="${1:-$(pbpaste)}"
  input="${input//$'\n'/ }"
  input="${${input##[[:space:]]#}%%[[:space:]]#}"
  [[ -n "$input" ]] || { print -u2 "❌ The clipboard is empty: copy a YouTube link first."; exit 1; }
  [[ "$input" =~ '(youtube\.com|youtu\.be|youtube-nocookie\.com)/' ]] \
    || { print -u2 "❌ Not a YouTube link: ${input[1,100]}"; exit 1; }

  JOB="summary-$(date +%Y-%m-%d_%H%M%S)"
  JOBDIR="$REPORTS/.jobs/$JOB"
  mkdir -p "$JOBDIR"
  status starting "Checking the link" "url=$input"
  python3 "$DIR/render_report.py" --pending "$JOB" "$REPORTS/$JOB.html" "$input"
  ensure_server
  [[ -n "${YT_SUMMARY_NO_OPEN:-}" ]] || open "http://localhost:$PORT/$JOB.html"
  print "$JOB"
}

step_transcript() {
  set_job "$1"
  status transcript "Fetching the transcript"
  python3 "$EXTRACT" "$URL" --out "$JOBDIR/transcript.txt" > /dev/null 2> "$JOBDIR/transcript.log" \
    || fail transcript "$(grep -v -i warn "$JOBDIR/transcript.log" | tail -1)"
  local title="$(sed -n 's/^Title: //p' "$JOBDIR/transcript.txt" | head -1)"
  local words="$(wc -w < "$JOBDIR/transcript.txt" | tr -d ' ')"
  [[ "$title" == unknown ]] && title=""
  status transcript "Transcript ready (~$words words)" "title=$title"
  print "$JOB"
}

step_summarize() {
  set_job "$1"
  status summarizing "Starting Claude"
  cd "$DIR"
  claude -p "/youtube-summarizer $URL" \
      --append-system-prompt "You are running non-interactively: never ask questions, pick sensible defaults. Do not save any file. The transcript has already been extracted, with the skill's own script, to $JOBDIR/transcript.txt: read that file instead of running the extraction script. Your final message must contain ONLY the complete Markdown report, with no preamble or closing remarks." \
      --allowedTools "Skill" "Read" "Bash(python3:*)" "Bash(pip:*)" "Bash(pip3:*)" "Bash(echo:*)" \
      --output-format stream-json --verbose --include-partial-messages 2> "$JOBDIR/claude.stderr.log" \
    | python3 "$DIR/job_status.py" stream "$JOBDIR/status.json" "$REPORTS/$JOB.md" "$JOBDIR/claude.jsonl" \
    || {
      # Prefer Claude's own error output; otherwise keep the message set by job_status.py.
      [[ -s "$JOBDIR/claude.stderr.log" ]] && fail summarizing "$(tail -3 "$JOBDIR/claude.stderr.log")"
      print -u2 "❌ Claude failed: see $JOBDIR/"
      exit 1
    }
  print "$JOB"
}

step_finish() {
  set_job "$1"
  status rendering "Building the page"
  python3 "$DIR/render_report.py" "$REPORTS/$JOB.md" "$REPORTS/$JOB.html" "$URL" \
    || fail rendering "Could not render the page"
  status done "Done"
  print "$JOB"
}

case "${1:-}" in
  start)      step_start "${2:-}" ;;
  transcript) step_transcript "${2:-}" ;;
  summarize)  step_summarize "${2:-}" ;;
  finish)     step_finish "${2:-}" ;;
  *)
    JOB="$(step_start "${1:-}")"
    step_transcript "$JOB" > /dev/null
    step_summarize "$JOB" > /dev/null
    step_finish "$JOB" > /dev/null
    print "Report: $REPORTS/$JOB.md"
    ;;
esac
