#!/usr/bin/env python3
"""
Render a youtube-summarizer report as an HTML page.

Usage:
  render_report.py REPORT.md OUTPUT.html [VIDEO_URL_OR_ID]
  render_report.py --pending JOB OUTPUT.html VIDEO_URL_OR_ID

The first form embeds the Markdown report in the page. The --pending form
creates the page before the report exists: it polls .jobs/JOB/status.json
for live progress, then loads JOB.md and shows it in place once the job is
done, without reloading (so the video keeps playing).

The video is embedded under the title. Any report heading containing a
timestamp, e.g. "### 2. The Monkey takes the wheel (04:05 – 05:50)", becomes
a link that seeks the player to that time. The player floats in a corner
while playing if you scroll past it.

YouTube refuses to play embeds on file:// pages (error 153), so the page must
be served over http (youtube-summary.sh runs a localhost server for that).
"""

import html
import json
import re
import sys

VIDEO_ID_RE = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")


def find_video_id(*texts):
    for text in texts:
        if not text:
            continue
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", text.strip()):
            return text.strip()
        match = VIDEO_ID_RE.search(text)
        if match:
            return match.group(1)
    return None


TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js" integrity="sha384-948ahk4ZmxYVYOc+rxN1H2gM1EJ2Duhp7uHtZ4WSLkV4Vtx5MUqnV+l7u9B+jFv+" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.2.6/dist/purify.min.js" integrity="sha384-JEyTNhjM6R1ElGoJns4U2Ln4ofPcqzSsynQkmEc/KGy6336qAZl70tDLufbkla+3" crossorigin="anonymous"></script>
<style>
:root { --fg: #1f2328; --muted: #59636e; --bg: #fff; --rule: #d1d9e0; --code: #f6f8fa; --link: #0969da; --hover: #eef4ff; --ok: #1a7f37; --err: #cf222e; --card: #f6f8fa; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #e6edf3; --muted: #9198a1; --bg: #0d1117; --rule: #3d444d; --code: #161b22; --link: #4493f8; --hover: #1a2433; --ok: #3fb950; --err: #f85149; --card: #161b22; }
}
body { font: 16px/1.6 -apple-system, "Helvetica Neue", sans-serif; color: var(--fg); background: var(--bg); max-width: 820px; margin: 0 auto; padding: 24px 16px 80px; }
h1 { font-size: 2em; line-height: 1.25; border-bottom: 1px solid var(--rule); padding-bottom: .3em; }
h2 { font-size: 1.5em; margin-top: 2em; border-bottom: 1px solid var(--rule); padding-bottom: .2em; }
h3 { font-size: 1.2em; margin-top: 1.6em; }
a { color: var(--link); }
code { background: var(--code); padding: 1px 5px; border-radius: 4px; font-size: .9em; }
pre { background: var(--code); padding: 12px; border-radius: 6px; overflow-x: auto; }
blockquote { border-left: 3px solid var(--rule); margin-left: 0; padding-left: 1em; color: var(--muted); }
hr { border: 0; border-top: 1px solid var(--rule); }
table { border-collapse: collapse; } td, th { border: 1px solid var(--rule); padding: 4px 8px; }

#video-slot { aspect-ratio: 16 / 9; margin: 1em 0 1.5em; }
#video { width: 100%; height: 100%; }
#video iframe { width: 100%; height: 100%; border: 0; border-radius: 8px; }
#video.floating { position: fixed; right: 16px; bottom: 16px; width: min(400px, calc(100vw - 32px)); height: auto; aspect-ratio: 16 / 9; z-index: 10; box-shadow: 0 8px 30px rgba(0,0,0,.35); border-radius: 8px; }

a.seek { color: inherit; text-decoration: none; cursor: pointer; border-radius: 4px; }
a.seek::before { content: "▶ "; color: var(--link); font-size: .8em; }
a.seek:hover { background: var(--hover); color: var(--link); }

#progress { background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 16px 20px; }
#progress[hidden] { display: none; }
#progress .head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
#progress .message { font-weight: 600; }
#progress .elapsed { color: var(--muted); font-variant-numeric: tabular-nums; }
#steps { list-style: none; padding: 0; margin: 12px 0; }
#steps li { padding: 3px 0; color: var(--muted); }
#steps li::before { display: inline-block; width: 1.6em; content: "○"; }
#steps li.active { color: var(--fg); font-weight: 600; }
#steps li.active::before { content: "◐"; animation: spin 1s linear infinite; }
#steps li.done::before { content: "✓"; color: var(--ok); }
#steps li.failed { color: var(--err); }
#steps li.failed::before { content: "✗"; }
@keyframes spin { 0% { content: "◐"; } 25% { content: "◓"; } 50% { content: "◑"; } 75% { content: "◒"; } }
#activity { font: 13px/1.5 ui-monospace, Menlo, monospace; color: var(--muted); border-top: 1px solid var(--rule); padding-top: 8px; margin: 0; list-style: none; padding-left: 0; }
#activity li { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#error { color: var(--err); white-space: pre-wrap; }
</style>
</head><body>
<header><h1 id="title">__TITLE__</h1></header>
<div id="video-slot" hidden><div id="video"><div id="yt"></div></div></div>
<section id="progress" hidden>
  <div class="head"><span class="message" id="message">Starting…</span><span class="elapsed" id="elapsed"></span></div>
  <ol id="steps">
    <li data-step="starting">Check the link</li>
    <li data-step="transcript">Fetch the transcript</li>
    <li data-step="summarizing">Write the summary with Claude</li>
    <li data-step="rendering">Build the page</li>
  </ol>
  <p id="error" hidden></p>
  <ul id="activity"></ul>
</section>
<article id="report"></article>
<script>
const VIDEO_ID = __VIDEO_ID__;
const MARKDOWN = __MARKDOWN__;
const JOB = __JOB__;
const STEPS = ["starting", "transcript", "summarizing", "rendering", "done"];

const $ = id => document.getElementById(id);
const report = $("report");
let player = null, playerReady = false, pendingSeek = null;

function toSeconds(stamp) {
  return stamp.split(":").reduce((total, part) => total * 60 + Number(part), 0);
}

function seek(seconds) {
  if (playerReady) {
    player.seekTo(seconds, true);
    player.playVideo();
  } else {
    pendingSeek = seconds;
  }
  const slot = $("video-slot").getBoundingClientRect();
  if (slot.bottom < 0 || slot.top > innerHeight) updateFloating(true);
}

function showReport(markdown) {
  report.innerHTML = DOMPurify.sanitize(marked.parse(markdown, { breaks: true }));
  // The report's own title replaces the page header, above the video.
  const h1 = report.querySelector("h1");
  if (h1) {
    $("title").textContent = h1.textContent;
    document.title = h1.textContent;
    h1.remove();
  }
  if (!VIDEO_ID) return;
  // Headings with a timestamp ("(04:05 – 05:50)", "[1:02:03]") seek the video.
  report.querySelectorAll("h2, h3, h4").forEach(h => {
    const match = h.textContent.match(/\\b(?:\\d{1,2}:)?\\d{1,2}:\\d{2}\\b/);
    if (!match) return;
    const seconds = toSeconds(match[0]);
    const link = document.createElement("a");
    link.className = "seek";
    link.href = "#t=" + seconds;
    link.title = "Play from " + match[0];
    link.append(...h.childNodes);
    link.addEventListener("click", e => { e.preventDefault(); seek(seconds); });
    h.append(link);
  });
}

// ---- Video player -------------------------------------------------------
let slotVisible = true;
function updateFloating(force) {
  if (!VIDEO_ID) return;
  const playing = playerReady && [YT.PlayerState.PLAYING, YT.PlayerState.BUFFERING].includes(player.getPlayerState());
  $("video").classList.toggle("floating", !slotVisible && (playing || force === true));
}

if (VIDEO_ID) {
  $("video-slot").hidden = false;
  window.onYouTubeIframeAPIReady = () => {
    player = new YT.Player("yt", {
      videoId: VIDEO_ID,
      playerVars: { rel: 0, playsinline: 1 },
      events: {
        onReady: () => {
          playerReady = true;
          if (pendingSeek !== null) seek(pendingSeek);
        },
        onStateChange: () => updateFloating(),
      },
    });
  };
  const api = document.createElement("script");
  api.src = "https://www.youtube.com/iframe_api";
  document.head.append(api);
  new IntersectionObserver(([entry]) => { slotVisible = entry.isIntersecting; updateFloating(); })
    .observe($("video-slot"));
}

// ---- Live progress (pending pages) --------------------------------------
function fmtElapsed(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
}

function renderStatus(status) {
  if (status.title) {
    $("title").textContent = status.title;
    document.title = "⏳ " + status.title;
  }
  $("message").textContent = status.message || "Working…";
  const failed = status.state === "error";
  const current = STEPS.indexOf(failed ? status.failed_step || "starting" : status.state);
  document.querySelectorAll("#steps li").forEach(li => {
    const index = STEPS.indexOf(li.dataset.step);
    li.className = index < current ? "done" : index > current ? "" : failed ? "failed" : "active";
  });
  $("activity").replaceChildren(...(status.activity || []).slice(-5).map(a => {
    const li = document.createElement("li");
    li.textContent = "[" + fmtElapsed(a.t - status.started_at) + "] " + a.text;
    return li;
  }));
}

async function poll() {
  let status;
  try {
    const response = await fetch(".jobs/" + JOB + "/status.json?t=" + Date.now(), { cache: "no-store" });
    // The job folder is deleted after a successful run: fall back to the finished report.
    status = response.status === 404 ? { state: "done" } : await response.json();
  } catch (e) {
    return setTimeout(poll, 2000);
  }
  renderStatus(status);
  if (status.state === "done") {
    const response = await fetch(JOB + ".md?t=" + Date.now(), { cache: "no-store" });
    if (!response.ok) return setTimeout(poll, 2000);
    showReport(await response.text());
    $("progress").hidden = true;
    clearInterval(ticker);
  } else if (status.state === "error") {
    $("message").textContent = "Failed";
    $("error").hidden = false;
    $("error").textContent = status.message + "\\n\\nLog: reports/.jobs/" + JOB + "/";
    document.title = "✗ " + document.title.replace(/^⏳ /, "");
    clearInterval(ticker);
  } else {
    startedAt = status.started_at;
    setTimeout(poll, 1500);
  }
}

let startedAt = null, ticker = null;
if (MARKDOWN !== null) {
  showReport(MARKDOWN);
} else {
  $("progress").hidden = false;
  ticker = setInterval(() => {
    if (startedAt) $("elapsed").textContent = fmtElapsed(Date.now() / 1000 - startedAt);
  }, 1000);
  poll();
}
</script>
</body></html>
"""


def render(path, title, video_id, markdown=None, job=None):
    page = (
        TEMPLATE.replace("__TITLE__", html.escape(title))
        .replace("__VIDEO_ID__", json.dumps(video_id))
        .replace("__JOB__", json.dumps(job))
        .replace("__MARKDOWN__", json.dumps(markdown).replace("</", "<\\/"))
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def main():
    args = sys.argv[1:]
    if len(args) == 4 and args[0] == "--pending":
        _, job, html_path, source = args
        render(html_path, "Summarizing video…", find_video_id(source), job=job)
    elif len(args) in (2, 3):
        md_path, html_path = args[:2]
        source = args[2] if len(args) == 3 else ""
        markdown = open(md_path, encoding="utf-8").read()
        title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "YouTube Summary"
        render(html_path, title, find_video_id(source, markdown), markdown=markdown)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
