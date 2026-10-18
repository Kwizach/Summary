#!/usr/bin/env python3
"""
Render a youtube-summarizer Markdown report as a standalone HTML page.

Usage: render_report.py REPORT.md OUTPUT.html [VIDEO_URL_OR_ID]

The video is embedded right after the title. Any heading containing a
timestamp, e.g. "### 2. The Monkey takes the wheel (04:05 – 05:50)", becomes
a link that seeks the embedded player to that time. The player floats in a
corner while playing if you scroll past it.

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
:root { --fg: #1f2328; --muted: #59636e; --bg: #fff; --rule: #d1d9e0; --code: #f6f8fa; --link: #0969da; --hover: #eef4ff; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #e6edf3; --muted: #9198a1; --bg: #0d1117; --rule: #3d444d; --code: #161b22; --link: #4493f8; --hover: #1a2433; }
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
</style>
</head><body>
<article id="report"></article>
<script>
const VIDEO_ID = __VIDEO_ID__;
const report = document.getElementById("report");
report.innerHTML = DOMPurify.sanitize(marked.parse(__MARKDOWN__, { breaks: true }));

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
  const slot = document.getElementById("video-slot").getBoundingClientRect();
  if (slot.bottom < 0 || slot.top > innerHeight) updateFloating(true);
}

if (VIDEO_ID) {
  // Embed the video right after the title.
  const slot = document.createElement("div");
  slot.id = "video-slot";
  slot.innerHTML = '<div id="video"><div id="yt"></div></div>';
  const h1 = report.querySelector("h1");
  h1 ? h1.after(slot) : report.prepend(slot);

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

  // While the video plays, float it in a corner when its slot scrolls away.
  let slotVisible = true;
  function updateFloating(force) {
    const playing = playerReady && [YT.PlayerState.PLAYING, YT.PlayerState.BUFFERING].includes(player.getPlayerState());
    document.getElementById("video").classList.toggle("floating", !slotVisible && (playing || force === true));
  }
  new IntersectionObserver(([entry]) => { slotVisible = entry.isIntersecting; updateFloating(); })
    .observe(slot);
}
</script>
</body></html>
"""


def main():
    if len(sys.argv) < 3:
        sys.exit("Usage: render_report.py REPORT.md OUTPUT.html [VIDEO_URL_OR_ID]")
    md_path, html_path = sys.argv[1], sys.argv[2]
    source = sys.argv[3] if len(sys.argv) > 3 else ""
    markdown = open(md_path, encoding="utf-8").read()

    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "YouTube Summary"

    page = (
        TEMPLATE.replace("__TITLE__", html.escape(title))
        .replace("__VIDEO_ID__", json.dumps(find_video_id(source, markdown)))
        .replace("__MARKDOWN__", json.dumps(markdown).replace("</", "<\\/"))
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main()
