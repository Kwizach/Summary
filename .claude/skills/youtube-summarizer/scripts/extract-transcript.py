#!/usr/bin/env python3
"""
Extract a YouTube video's metadata and timestamped transcript.

Usage:
  extract-transcript.py URL_OR_ID [--lang CODE] [--out FILE]
  extract-transcript.py URL_OR_ID --list

Accepts watch, youtu.be, shorts, embed, live and mobile URLs, or a bare
11-character video ID. Without --lang, the video's original-language
transcript is used (manual captions preferred over auto-generated).

Output: a metadata header followed by transcript lines grouped into ~30s
blocks as "[MM:SS] text". Written to --out if given, otherwise stdout.

Exit codes: 0 ok, 1 invalid input, 2 no transcript available, 3 other error.
Requires youtube-transcript-api >= 1.0.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import warnings

warnings.filterwarnings("ignore")

try:
    from youtube_transcript_api import (
        YouTubeTranscriptApi,
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError:
    print("❌ youtube-transcript-api is not installed. Run: pip install -U youtube-transcript-api", file=sys.stderr)
    sys.exit(3)

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
BLOCK_SECONDS = 30


def parse_video_id(value):
    value = value.strip().strip("<>\"'")
    if ID_RE.match(value):
        return value
    if not re.match(r"^[a-z]+://", value):
        value = "https://" + value
    url = urllib.parse.urlparse(value)
    host = url.netloc.lower().removeprefix("www.").removeprefix("m.").removeprefix("music.")
    if host == "youtu.be":
        candidate = url.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        query = urllib.parse.parse_qs(url.query)
        if "v" in query:
            candidate = query["v"][0]
        else:
            parts = url.path.strip("/").split("/")
            candidate = parts[1] if len(parts) > 1 and parts[0] in ("shorts", "embed", "live", "v") else ""
    else:
        candidate = ""
    return candidate if ID_RE.match(candidate) else None


def fetch_metadata(video_id):
    """Title and channel via YouTube's public oEmbed endpoint (no API key)."""
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
        f"https://www.youtube.com/watch?v={video_id}", safe=""
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
        return {"title": data.get("title"), "channel": data.get("author_name")}
    except Exception:
        return {"title": None, "channel": None}


def pick_transcript(transcript_list, lang):
    transcripts = list(transcript_list)
    if lang:
        try:
            return transcript_list.find_transcript([lang])
        except NoTranscriptFound:
            # Fall back to translating the best available transcript.
            for t in transcripts:
                if t.is_translatable:
                    return t.translate(lang)
            print(f"⚠️  No '{lang}' transcript; using the original language", file=sys.stderr)
            return pick_transcript(transcript_list, None)
    # The original language is normally the auto-generated track's language;
    # prefer a manual transcript in that language when one exists.
    generated = [t for t in transcripts if t.is_generated]
    if generated:
        original = generated[0].language_code
        manual = [t for t in transcripts if not t.is_generated and t.language_code == original]
        return manual[0] if manual else generated[0]
    return transcripts[0]


def fmt_time(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def group_snippets(snippets):
    blocks, start, texts = [], None, []
    for snip in snippets:
        text = snip.text.replace("\n", " ").strip()
        if not text:
            continue
        if start is None:
            start = snip.start
        texts.append(text)
        if snip.start - start >= BLOCK_SECONDS:
            blocks.append(f"[{fmt_time(start)}] {' '.join(texts)}")
            start, texts = None, []
    if texts:
        blocks.append(f"[{fmt_time(start)}] {' '.join(texts)}")
    return blocks


def main():
    parser = argparse.ArgumentParser(description="Extract a YouTube transcript.")
    parser.add_argument("video", help="YouTube URL or video ID")
    parser.add_argument("--lang", help="transcript language code (default: original language)")
    parser.add_argument("--list", action="store_true", help="list available transcripts and exit")
    parser.add_argument("--out", help="write output to this file instead of stdout")
    args = parser.parse_args()

    video_id = parse_video_id(args.video)
    if not video_id:
        print(f"❌ Not a YouTube video URL or ID: {args.video}", file=sys.stderr)
        sys.exit(1)

    api = YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
        if args.list:
            for t in transcript_list:
                kind = "auto-generated" if t.is_generated else "manual"
                print(f"{t.language_code}\t{t.language}\t{kind}")
            return
        transcript = pick_transcript(transcript_list, args.lang)
        fetched = transcript.fetch()
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f"❌ No transcript available for {video_id}: {type(e).__name__}", file=sys.stderr)
        sys.exit(2)
    except VideoUnavailable:
        print(f"❌ Video {video_id} is unavailable, private or removed", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"❌ Error fetching transcript for {video_id}: {e}", file=sys.stderr)
        sys.exit(3)

    snippets = list(fetched)
    meta = fetch_metadata(video_id)
    duration = snippets[-1].start + snippets[-1].duration if snippets else 0
    header = [
        f"Title: {meta['title'] or 'unknown'}",
        f"Channel: {meta['channel'] or 'unknown'}",
        f"URL: https://www.youtube.com/watch?v={video_id}",
        f"Duration (approx.): {fmt_time(duration)}",
        f"Transcript: {transcript.language} ({transcript.language_code}), "
        f"{'auto-generated' if transcript.is_generated else 'manual'}",
        "",
        "--- TRANSCRIPT ---",
    ]
    output = "\n".join(header + group_snippets(snippets)) + "\n"

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ Saved to {args.out} ({len(output)} chars, {len(snippets)} segments)")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
