---
name: youtube-summarizer
description: "Extract the transcript of a YouTube video and write a comprehensive, structured Markdown summary report. Use when the user gives a YouTube URL (watch, youtu.be, shorts, live) and wants a summary, notes, key points or the transcript."
category: content
risk: safe
source: community
tags: "[video, summarization, transcription, youtube, content-analysis]"
date_added: "2026-02-27"
---

# youtube-summarizer

Turn a YouTube video into a detailed reference document, so the reader gets all the substance without watching it. Completeness beats brevity, but every sentence must carry information from the video.

## Step 1: Extract the transcript

Run the bundled script (it lives in this skill's `scripts/` directory). It accepts any YouTube URL form or a bare video ID, fetches title/channel, and writes a timestamped transcript:

```bash
python3 <skill-dir>/scripts/extract-transcript.py "<URL>" --out "${TMPDIR:-/tmp}/yt-transcript.txt"
```

Then read the output file with the Read tool. Always use `--out` + Read rather than printing to stdout: long transcripts get truncated in command output.

Options: `--list` shows available transcript languages; `--lang CODE` picks one (falls back to the original language if missing). The transcript language does not constrain the summary language; leave `--lang` off by default.

Exit codes and what to do:

| Code | Meaning | Action |
|------|---------|--------|
| 1 | Input isn't a YouTube video URL/ID | Tell the user, show an example URL, stop |
| 2 | No transcript, or video private/removed | Tell the user; the video can't be summarized from captions, stop |
| 3 | Missing dependency or network/API error | If the message says the package is missing, run `pip install -U youtube-transcript-api` and retry once; otherwise report the error and stop |

Never invent content for a video you could not get a transcript for.

## Step 2: Analyze

Before writing, work through the transcript:

1. **Identify the video type** (lecture, tutorial, interview/podcast, talk, review, news, story…) and adapt: tutorials need the exact steps and commands, interviews need who said what, arguments need the claims *and* their supporting evidence.
2. **Find the structure**: the topic shifts and where they occur (use the `[MM:SS]` markers).
3. **Collect the substance**: claims, reasoning, numbers, examples, anecdotes, recommendations, named tools/people/books/links, and memorable quotes.
4. **Clean up auto-caption noise**: auto-generated transcripts misspell names and jargon; correct them when context makes the right term obvious, and never quote a garbled phrase as if verbatim.

## Step 3: Write the report

Write in the language the user wrote their request in; if the request is only a URL or slash command, write in English. Use this structure:

```markdown
# <Video title>

**Channel:** <channel> · **Duration:** <duration> · **URL:** <url>
**Transcript:** <language>, <manual|auto-generated>

## Executive Summary
<1–3 paragraphs: what the video is about, its main thesis or purpose, and the most important conclusions. A reader who stops here should know the key takeaways.>

## Key Takeaways
- <5–10 bullets, each a complete, specific insight, not a topic label>

## Detailed Summary
### 1. <Section title> (MM:SS – MM:SS)
<Thorough account of this part: arguments with their reasoning, examples, data, steps, short quotes. Use sub-bullets or #### subsections when it helps.>
### 2. …

## Concepts and Terminology
- **<Term>:** <definition as used in the video>

## Resources Mentioned
- <books, tools, people, links, products named in the video>

## Conclusion
<Final synthesis: the speaker's closing message, and any caveats or open questions worth noting.>
```

Guidelines:
- Scale length to the content: a 2-minute clip gets a short report; a 2-hour lecture gets a long one. Omit sections that would be empty (e.g. no resources mentioned) rather than padding them.
- Attribute views to the speaker ("the speaker argues…") instead of presenting them as fact; flag claims that are notably disputed or outdated.
- Every `###` heading in Detailed Summary must end with its time range in the form `(MM:SS – MM:SS)` (or `H:MM:SS` past an hour), taken from the transcript's `[MM:SS]` markers. The HTML viewer turns these headings into links that seek the embedded video, so use timestamps nowhere else in headings.
- Keep quotes short and exact; put timestamps on sections, not on every sentence.
- If title/channel came back as `unknown`, say so; don't guess them.

## Step 4: Deliver

Reply with the full Markdown report. Only save it to a file if the user asks (and then also append the raw transcript if they ask for it). Don't ask follow-up questions unless something is genuinely ambiguous: when run non-interactively there's nobody to answer.
