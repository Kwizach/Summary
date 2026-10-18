#!/usr/bin/env python3
"""
Maintain a summary job's status.json, which the report page polls for live progress.

Usage:
  job_status.py set STATUS.json STATE [MESSAGE] [key=value ...]
  job_status.py get STATUS.json KEY
  job_status.py stream STATUS.json REPORT.md RAW.log < claude-stream-json

`stream` reads Claude Code's `--output-format stream-json --verbose
--include-partial-messages` output, turns tool calls and text deltas into
human-readable activity, and writes the final result text to REPORT.md.
Exits 1 if Claude reported an error or produced no result.

STATE is one of: starting, transcript, summarizing, rendering, done, error.
"""

import json
import os
import sys
import time

ACTIVITY_LIMIT = 8


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(path, status):
    status["updated_at"] = time.time()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)
    os.replace(tmp, path)


def update(path, state=None, message=None, **fields):
    status = load(path)
    status.setdefault("started_at", time.time())
    status.setdefault("activity", [])
    if state:
        status["state"] = state
    if message is not None:
        status["message"] = message
    status.update(fields)
    save(path, status)
    return status


def add_activity(path, text):
    status = load(path)
    activity = status.get("activity", [])
    activity.append({"t": time.time(), "text": text})
    status["activity"] = activity[-ACTIVITY_LIMIT:]
    save(path, status)


def describe_tool(name, tool_input):
    if name == "Skill":
        return f"Loading the {tool_input.get('skill', '')} skill"
    if name == "Read":
        target = os.path.basename(tool_input.get("file_path", ""))
        return "Reading the transcript" if target.endswith("transcript.txt") else f"Reading {target}"
    if name == "Bash":
        command = " ".join(tool_input.get("command", "").split())
        return "Running: " + (command[:70] + "…" if len(command) > 70 else command)
    return f"Using {name}"


def stream(status_path, md_path, raw_path):
    result, is_error = None, False
    words, chars, last_write = 0, 0, 0.0
    with open(raw_path, "a", encoding="utf-8") as raw:
        for line in sys.stdin:
            raw.write(line)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get("type")

            if kind == "stream_event":
                delta = event.get("event", {}).get("delta", {})
                if delta.get("type") == "text_delta":
                    if chars == 0:
                        add_activity(status_path, "Writing the summary")
                    chars += len(delta.get("text", ""))
                    words = chars // 6
                    if time.time() - last_write > 1:
                        update(status_path, message=f"Writing the summary… ~{words:,} words")
                        last_write = time.time()
            elif kind == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use":
                        text = describe_tool(block.get("name", ""), block.get("input", {}))
                        add_activity(status_path, text)
                        update(status_path, message=text)
                chars = 0  # each assistant turn restarts the word count
            elif kind == "result":
                result = event.get("result")
                is_error = bool(event.get("is_error"))
                update(status_path, cost_usd=event.get("total_cost_usd"))

    if is_error or not result:
        update(status_path, "error", (result or "Claude produced no output")[:500], failed_step="summarizing")
        return 1
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(result.strip() + "\n")
    return 0


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    command, path = sys.argv[1], sys.argv[2]
    if command == "set":
        state = sys.argv[3] if len(sys.argv) > 3 else None
        message = sys.argv[4] if len(sys.argv) > 4 else None
        fields = dict(arg.split("=", 1) for arg in sys.argv[5:])
        update(path, state, message, **fields)
        if message and state not in ("error",):
            add_activity(path, message)
    elif command == "get":
        print(load(path).get(sys.argv[3], ""))
    elif command == "stream":
        sys.exit(stream(path, sys.argv[3], sys.argv[4]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
