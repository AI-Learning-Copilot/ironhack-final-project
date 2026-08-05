# data/raw

**The transcripts are not in git.** The repo is public and the recordings contain
classmates' names and classroom conversations. `captions/` is gitignored.

## Get them (~4 minutes)

```bash
bash data/raw/fetch_captions.sh
```

Downloads the transcript (`.vtt`) and metadata (`.info.json`) for all 122 Loom
recordings listed in `looms.txt`. No video is downloaded. Idempotent — re-running skips
anything already present.

Requires `yt-dlp` (`brew install yt-dlp`) and Loom access to the cohort recordings.

## What you get

| | |
|---|---|
| Recordings | 122 across 33 lesson days (`w1d1` → `w8d2`) |
| Runtime | 91.4 hours |
| Transcripts | 120 — `w3d4-d` (standup intro) and `w6d2-a` (Project-3 kickoff) have no captions on Loom |
| Size | 8.8 MB |

Filenames are `<lesson_day>__<loom_id>.en.vtt`. Each `.info.json` carries the Loom
title, e.g. `AI 2026.06 - w7d2 - b - RAG II - Indexing` — that is where lesson titles
come from, so nothing is typed by hand.

## Before indexing

Strip classmates' names during ingestion, not just for privacy — classroom chatter
("Hi Alice", "can everyone open their cameras") is retrieval noise that competes with
actual teaching content.
