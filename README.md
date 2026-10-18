# YouTube Summary

Copy a YouTube link and run a Shortcut. A page opens in your browser right away with the video embedded and live progress (steps, elapsed time, what Claude is doing, words written so far). When the summary is ready, usually in 1–3 minutes, it appears on the same page. Click any section heading in **Detailed Summary** and the video jumps to that part. If you've scrolled away, the player floats in the bottom-right corner while it plays.

It works in three layers, each usable on its own:

| Layer | File | What it does |
|-------|------|--------------|
| Skill | `.claude/skills/youtube-summarizer/` | Teaches Claude Code to fetch a transcript and write the report (`/youtube-summarizer <url>`) |
| Script | `youtube-summary.sh` + `render_report.py` + `job_status.py` | Runs Claude headless on the link, shows live progress, saves the report as `.md` + `.html` |
| Shortcut | `YouTube Summary.shortcut` | Runs the script's steps on whatever is in the clipboard, with notifications |

```
.
├── .claude/skills/youtube-summarizer/
│   ├── SKILL.md                     # instructions Claude follows
│   └── scripts/extract-transcript.py
├── youtube-summary.sh               # clipboard/URL → report → browser (all steps, or one step at a time)
├── render_report.py                 # builds the page: live progress, then report + embed + seek links
├── job_status.py                    # writes the progress the page shows
├── YouTube Summary.shortcut         # macOS Shortcuts file
└── reports/
    ├── summary-<date>.md / .html    # your reports
    └── .jobs/summary-<date>/        # per-run status, transcript and logs
```

## Requirements

- macOS with the Shortcuts app
- [Claude Code](https://docs.claude.com/en/docs/claude-code) installed and logged in (`claude` works in a terminal)
- Python 3 with `youtube-transcript-api` 1.0 or later:
  ```bash
  pip install -U "youtube-transcript-api>=1.0"
  ```
  or run `.claude/skills/youtube-summarizer/scripts/install-dependencies.sh`
- An internet connection (transcripts, and the page loads its Markdown renderer and the YouTube player from CDNs)

## 1. The skill

The skill is already active for Claude Code sessions started in this folder:

```bash
cd ~/Agents/Youtube/Summary
claude
> /youtube-summarizer https://www.youtube.com/watch?v=arj7oStGLkU
```

To use it from **any** folder, copy it to your personal skills directory:

```bash
cp -R .claude/skills/youtube-summarizer ~/.claude/skills/
```

The transcript script also works on its own:

```bash
python3 .claude/skills/youtube-summarizer/scripts/extract-transcript.py "<url>"            # print transcript
python3 .claude/skills/youtube-summarizer/scripts/extract-transcript.py "<url>" --list     # available languages
python3 .claude/skills/youtube-summarizer/scripts/extract-transcript.py "<url>" --out t.txt
```

> ⚠️ Don't run `scripts/update.sh`: it replaces the skill with the upstream version, whose transcript script is broken with current `youtube-transcript-api`.

## 2. The script

```bash
./youtube-summary.sh "https://youtu.be/arj7oStGLkU"   # summarize this link
./youtube-summary.sh                                  # summarize the link in the clipboard
```

It runs four steps, which the Shortcut calls one at a time (`./youtube-summary.sh start|transcript|summarize|finish`):

| Step | What it does |
|------|--------------|
| `start [URL]` | Checks it's a YouTube link, opens the live progress page at `http://localhost:47821/summary-<date>.html`, prints the job name |
| `transcript JOB` | Fetches the transcript with the skill's script (fails fast if the video has no captions) |
| `summarize JOB` | Runs `claude -p "/youtube-summarizer <link>"` in this folder and streams its activity to the page. Claude reads the already-fetched transcript, and may only use the skill, read files and run `python3`/`pip`/`echo`, because the link and transcript are untrusted text |
| `finish JOB` | Saves `summary-<date>.md`, rebuilds `summary-<date>.html` with the report embedded, and marks the job done. The open page then shows the report without reloading, so the video keeps playing |

If a step fails, the page shows which one and why, and the Shortcut stops with the error. Logs are in `reports/.jobs/summary-<date>/`.

**Why localhost?** YouTube refuses to play embedded videos on pages opened from a file (`file://…`, "Error 153"). So the script starts a small web server the first time it runs. The server is bound to `127.0.0.1` and serves only `reports/`, and it keeps running in the background until you log out. Open `http://localhost:47821/` to browse all your reports.

- Use another port: `YT_SUMMARY_PORT=8800 ./youtube-summary.sh`
- Stop the server: `pkill -f "http.server 47821"` (the next run starts it again)
- Re-render an existing report: `python3 render_report.py reports/X.md reports/X.html`

## 3. The Shortcut

1. Double-click **`YouTube Summary.shortcut`** and click **Add Shortcut**.
2. In Shortcuts, open **Settings → Advanced** and turn on **Allow Running Scripts**.
3. Optional: in the shortcut's details (ⓘ), pin it to the menu bar or add a keyboard shortcut.

**Updating from an older version:** delete the old "YouTube Summary" shortcut first, otherwise the import creates "YouTube Summary 1".

Then copy a YouTube link and run the Shortcut. The progress page opens in your browser within a second or two, and you get a notification at each stage. The Shortcuts icon in the menu bar fills up as the shortcut moves through its 7 actions:

| # | Action | |
|---|--------|---|
| 1 | Run Shell Script | `"…/youtube-summary.sh" start` |
| 2 | Show Notification | "Fetching the transcript…" |
| 3 | Run Shell Script | `"…/youtube-summary.sh" transcript "$1"` (input: result of 1, as arguments) |
| 4 | Show Notification | "Claude is writing the summary…" |
| 5 | Run Shell Script | `"…/youtube-summary.sh" summarize "$1"` (input: result of 3) |
| 6 | Run Shell Script | `"…/youtube-summary.sh" finish "$1"` (input: result of 5) |
| 7 | Show Notification | "Summary ready ✓" |

The menu bar meter counts actions, not time, so it sits at action 5 while Claude writes. The browser page shows the real progress.

**If you move this folder**, edit the path in the four Run Shell Script actions.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Shortcut stops with an error | The message says why. Usually: `claude` not logged in, or the video has no captions. Details are in `reports/.jobs/<job>/` |
| "The clipboard is empty" / "Not a YouTube link" | Copy the video's link first |
| Page stuck on a step | Check the Shortcuts menu bar icon is still running, and look at `reports/.jobs/<job>/status.json` |
| Headings aren't clickable | The report has no `(MM:SS – MM:SS)` in its headings. Re-run, or add the timestamps to the `.md` and re-render |
| "Error 153" in the player | The page was opened as a file. Open it through `http://localhost:47821/` |
| Shortcut does nothing | Check **Allow Running Scripts** is on, and the path in the action is correct |
