# Gujju The Trader — transcript research collector

This isolated research utility collects **publicly available subtitle/caption tracks** from the Gujju The Trader channel. It does not download video or audio.

## Run locally

```bash
python -m pip install -r requirements-transcripts.txt
python scripts/gtt_transcript_collector.py
```

Optional:
- `--limit 25` collects only the first 25 discovered uploads.
- `--delay 3` increases the pause between video requests.
- `--output /path/to/folder` changes the output directory.

## GitHub Actions

Run **Actions → Gujju The Trader - collect channel transcripts → Run workflow**. Use `0` for the full channel or a smaller number for a test run. Download the resulting `gujju-the-trader-transcripts` artifact.

Outputs:
- `video_inventory.json`: discovered videos and per-video status
- `raw_vtt/`: original caption files
- `transcripts_txt/`: cleaned UTF-8 transcripts
- `summary.json`: honest totals, including videos with no captions and failures

The collector prefers the subtitle tracks exposed by YouTube/yt-dlp and requests all available languages. A video with no accessible caption track is marked as such; it is not represented as learned. YouTube may rate-limit cloud runners, and some videos may be private, members-only, region-restricted, or caption-disabled. Re-run later or run locally if the runner is blocked.

Use transcripts only in accordance with YouTube's terms and applicable copyright law. Keep the transcripts for private research; do not republish creators' full transcripts.
