#!/bin/bash
# Downloads the transcript (.vtt) + metadata (.info.json) for every Loom in looms.txt.
# No video is downloaded. Files land in captions/ named <day>__<loom_id>.*
cd "$(dirname "$0")"
mkdir -p captions
ok=0; fail=0
while read -r day id; do
  [ -z "$id" ] && continue
  if [ -f "captions/${day}__${id}.en.vtt" ]; then
    echo "SKIP  $day $id (already have it)"
    ok=$((ok+1)); continue
  fi
  if yt-dlp --write-subs --sub-format vtt --skip-download --write-info-json \
       --no-warnings --quiet \
       -o "captions/${day}__${id}.%(ext)s" \
       "https://www.loom.com/share/$id" 2>>fetch_errors.log; then
    echo "OK    $day $id"
    ok=$((ok+1))
  else
    echo "FAIL  $day $id"
    fail=$((fail+1))
  fi
  sleep 1
done < looms.txt
echo "=== done: $ok ok, $fail failed ==="
