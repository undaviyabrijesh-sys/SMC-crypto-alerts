#!/usr/bin/env python3
"""Collect publicly available captions from the Gujju The Trader YouTube channel.

This downloads subtitle/caption tracks only (not video or audio). It preserves raw
VTT files and writes readable UTF-8 text files plus a video inventory.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

DEFAULT_CHANNEL = "https://www.youtube.com/@gujjuthetrader2787/videos"


def clean_vtt(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    output: list[str] = []
    previous = ""
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line == "WEBVTT" or line.startswith(("NOTE", "Kind:", "Language:")):
            continue
        if "-->" in line or re.fullmatch(r"\d+", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = (line.replace("&amp;", "&").replace("&lt;", "<")
                    .replace("&gt;", ">").replace("&quot;", '"'))
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        # YouTube rolling captions often repeat the previous cue with an extension.
        if line == previous:
            continue
        if previous and line.startswith(previous):
            addition = line[len(previous):].strip()
            if addition:
                output.append(addition)
        else:
            output.append(line)
        previous = line
    return "\n".join(output).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel-url", default=DEFAULT_CHANNEL)
    parser.add_argument("--output", default="artifacts/gujju-the-trader")
    parser.add_argument("--limit", type=int, default=0,
                        help="Optional maximum videos; 0 means all discovered videos.")
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    root = Path(args.output)
    raw_dir = root / "raw_vtt"
    text_dir = root / "transcripts_txt"
    raw_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    list_opts = {
        "skip_download": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
    }
    with YoutubeDL(list_opts) as ydl:
        channel = ydl.extract_info(args.channel_url, download=False)

    entries = [e for e in (channel or {}).get("entries", []) if e and e.get("id")]
    if args.limit > 0:
        entries = entries[:args.limit]

    inventory: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        video_id = entry["id"]
        url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        if not str(url).startswith("http"):
            url = f"https://www.youtube.com/watch?v={video_id}"
        inventory.append({
            "index": index,
            "id": video_id,
            "title": entry.get("title", ""),
            "url": url,
            "upload_date": entry.get("upload_date"),
            "duration": entry.get("duration"),
            "status": "queued",
        })

    (root / "video_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Discovered {len(inventory)} videos")

    for item in inventory:
        video_id = item["id"]
        options = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["all"],
            "subtitlesformat": "vtt/best",
            "outtmpl": str(raw_dir / "%(id)s.%(ext)s"),
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 2,
            "extractor_retries": 2,
            "sleep_interval": 1,
            "max_sleep_interval": 3,
        }
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([item["url"]])
            tracks = sorted(raw_dir.glob(f"{video_id}*.vtt"))
            if tracks:
                for track in tracks:
                    clean = clean_vtt(track)
                    lang_match = re.search(r"\.([A-Za-z0-9_-]+)\.vtt$", track.name)
                    lang = lang_match.group(1) if lang_match else "unknown"
                    out = text_dir / f"{video_id}.{lang}.txt"
                    out.write_text(clean, encoding="utf-8")
                item["status"] = "captions_downloaded"
                item["tracks"] = [p.name for p in tracks]
            else:
                item["status"] = "no_caption_track_found"
        except Exception as exc:  # continue through the channel if one video fails
            item["status"] = "failed"
            item["error"] = str(exc)[:500]

        (root / "video_inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[{item['index']}/{len(inventory)}] {item['status']}: {item['title']}")
        time.sleep(max(0.0, args.delay))

    summary = {
        "channel_url": args.channel_url,
        "videos_discovered": len(inventory),
        "videos_with_captions": sum(x["status"] == "captions_downloaded" for x in inventory),
        "videos_without_captions": sum(x["status"] == "no_caption_track_found" for x in inventory),
        "videos_failed": sum(x["status"] == "failed" for x in inventory),
        "transcript_files": len(list(text_dir.glob("*.txt"))),
        "note": "Caption availability depends on each video's public manual/automatic subtitle tracks.",
    }
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
