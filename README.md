# YouTube Summary

Copy a YouTube link, run a Shortcut, and a few minutes later a detailed summary opens in your browser, with the video embedded under the title. Click any section heading in **Detailed Summary** and the video jumps to that part. If you've scrolled away, the player floats in the bottom-right corner while it plays.

It works in three layers, each usable on its own:

| Layer | File | What it does |
|-------|------|--------------|
| Skill | `.claude/skills/youtube-summarizer/` | Teaches Claude Code to fetch a transcript and write the report (`/youtube-summarizer <url>`) |
| Script | `youtube-summary.sh` + `render_report.py` | Runs Claude headless on the link, saves the report as `.md` + `.html`, opens it |
| Shortcut | `YouTube Summary.shortcut` | Runs the script on whatever is in the clipboard |

```
.
├── .claude/skills/youtube-summarizer/
│   ├── SKILL.md                     # instructions Claude follows
│   └── scripts/extract-transcript.py
├── youtube-summary.sh               # clipboard/URL → report → browser
├── render_report.py                 # report.md → report.html (embed + seek links)
├── YouTube Summary.shortcut         # macOS Shortcuts file
└── reports/                         # generated reports (.md, .html, .log)
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

What happens:

1. Runs `claude -p "/youtube-summarizer <link>"` in this folder. Claude may only use the skill, read files and run `python3`/`pip`/`echo`, because the link and transcript are untrusted text.
2. Saves the report to `reports/summary-<date>.md` and the run log to `reports/summary-<date>.log`.
3. Renders `reports/summary-<date>.html` with `render_report.py`.
4. Opens it at `http://localhost:47821/summary-<date>.html`.

**Why localhost?** YouTube refuses to play embedded videos on pages opened from a file (`file://…`, "Error 153"). So the script starts a small web server the first time it runs. The server is bound to `127.0.0.1` and serves only `reports/`, and it keeps running in the background until you log out. Open `http://localhost:47821/` to browse all your reports.

- Use another port: `YT_SUMMARY_PORT=8800 ./youtube-summary.sh`
- Stop the server: `pkill -f "http.server 47821"` (the next run starts it again)
- Re-render an existing report: `python3 render_report.py reports/X.md reports/X.html`

## 3. The Shortcut

1. Double-click **`YouTube Summary.shortcut`** and click **Add Shortcut**.
2. In Shortcuts, open **Settings → Advanced** and turn on **Allow Running Scripts**.
3. Optional: in the shortcut's details (ⓘ), pin it to the menu bar or add a keyboard shortcut.

Then copy a YouTube link and run the Shortcut. You get a "Summarizing video…" notification, and the page opens in your default browser when it's ready (usually 2–5 minutes, depending on the video's length).

The shortcut is a single **Run Shell Script** action (shell `zsh`) containing:

```
"/Users/clm/Agents/Youtube/Summary/youtube-summary.sh"
```

**If you move this folder**, edit that path in the shortcut, or rebuild it by hand with that one action.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Alert "YouTube Summary failed" | Read the `.log` file it names. Usually: `claude` not logged in, or no transcript for that video |
| Alert "The clipboard is empty" | Copy the link first |
| The page shows Claude's error message instead of a report | The clipboard didn't hold a YouTube link, or the video has no captions |
| Headings aren't clickable | The report has no `(MM:SS – MM:SS)` in its headings. Re-run, or add the timestamps to the `.md` and re-render |
| "Error 153" in the player | The page was opened as a file. Open it through `http://localhost:47821/` |
| Shortcut does nothing | Check **Allow Running Scripts** is on, and the path in the action is correct |
