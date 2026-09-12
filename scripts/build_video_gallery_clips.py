#!/usr/bin/env python3
"""Build lightweight 10 s gallery clips from existing MILD preview videos.

The source videos are the rosbag-synchronized front/back X5 and left/right
Insight9 previews produced for the earlier MILD website. This script creates
review-page-friendly local MP4 clips plus poster JPEGs and a JSON manifest used
by the static website.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


SOURCE_ROOT = Path(os.environ.get("MILD_SYNC_VIDEO_ROOT", "../MILD_video_previews/v0_sync_combined")).expanduser()
SITE_ROOT = Path(__file__).resolve().parents[1]
VIDEO_ROOT = SITE_ROOT / "assets" / "videos" / "gallery"
POSTER_ROOT = SITE_ROOT / "assets" / "posters" / "gallery"
MANIFEST_PATH = SITE_ROOT / "assets" / "videos" / "gallery_manifest.json"
CLIP_SECONDS = 10.0

TASK_LABELS = {
    "analemma_2_t": "Analemma 02",
    "circular_2_t": "Circular 02",
    "zigzag_2_t": "Zigzag 02",
    "bookshelf01_2": "Bookshelf 01",
    "bookshelf02_2": "Bookshelf 02",
    "box01": "Box 01",
    "box02": "Box 02",
    "grab_place01_t": "Pick-and-place 01",
    "grab_place02_t": "Pick-and-place 02",
    "grab_place03_t": "Pick-and-place 03",
    "grab_place04": "Pick-and-place 04",
    "grab_place05": "Pick-and-place 05",
    "grab_place06_t": "Pick-and-place 06",
    "wiping01": "Wiping 01",
    "wiping02_1": "Wiping 02",
}

TASK_ORDER = {slug: i for i, slug in enumerate(TASK_LABELS)}

SCENE_LABELS = {
    "table": "Plain table",
    "tablecloth": "Tablecloth",
    "apriltag_1": "AprilTag 1",
    "apriltag_2": "AprilTag 2",
    "apriltag_4": "AprilTag 4",
    "aruco_1": "ArUco 1",
    "aruco_2": "ArUco 2",
    "aruco_4": "ArUco 4",
}

SCENE_ORDER = {
    "table": 0,
    "tablecloth": 1,
    "apriltag_1": 2,
    "apriltag_2": 3,
    "apriltag_4": 4,
    "aruco_1": 5,
    "aruco_2": 6,
    "aruco_4": 7,
}

SENSORS = {
    "insta360_x5_front_back_sync.mp4": {
        "slug": "insta360-x5",
        "label": "Insta360 X5",
        "stream": "front / back fisheye",
        "scale": "960:-2",
    },
    "insight9_left_right_sync.mp4": {
        "slug": "insight9",
        "label": "Insight9",
        "stream": "left / right gray",
        "scale": "816:-2",
    },
}


def run(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def ffprobe_duration(path: Path) -> float:
    out = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(out)


def safe_slug(text: str) -> str:
    return text.replace("_", "-").lower()


def build_record(src: Path) -> dict:
    rel = src.relative_to(SOURCE_ROOT)
    task_slug = rel.parts[0]
    scene_slug = rel.parts[1]
    sensor_info = SENSORS[src.name]
    base = f"{safe_slug(task_slug)}__{safe_slug(scene_slug)}__{sensor_info['slug']}"
    out_mp4 = VIDEO_ROOT / f"{base}.mp4"
    out_jpg = POSTER_ROOT / f"{base}.jpg"
    duration = ffprobe_duration(src)
    start = max(0.0, (duration - CLIP_SECONDS) * 0.5)
    clip_duration = min(CLIP_SECONDS, duration)

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)

    if not out_mp4.exists() or out_mp4.stat().st_size == 0:
        run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{clip_duration:.3f}",
                "-i",
                str(src),
                "-vf",
                f"scale={sensor_info['scale']},fps=24",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-preset",
                "veryfast",
                "-crf",
                "31",
                str(out_mp4),
            ]
        )

    if not out_jpg.exists() or out_jpg.stat().st_size == 0:
        run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{min(duration, start + 1.0):.3f}",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-vf",
                f"scale={sensor_info['scale']}",
                "-q:v",
                "4",
                str(out_jpg),
            ]
        )

    return {
        "task_slug": task_slug,
        "task_label": TASK_LABELS.get(task_slug, task_slug),
        "scene_slug": scene_slug,
        "scene_label": SCENE_LABELS.get(scene_slug, scene_slug),
        "sensor_slug": sensor_info["slug"],
        "sensor_label": sensor_info["label"],
        "stream_label": sensor_info["stream"],
        "clip_seconds": round(clip_duration, 3),
        "source_seconds": round(duration, 3),
        "source_path": str(rel),
        "video": str(out_mp4.relative_to(SITE_ROOT)),
        "poster": str(out_jpg.relative_to(SITE_ROOT)),
        "size_bytes": out_mp4.stat().st_size,
    }


def main() -> None:
    sources = [
        path
        for path in SOURCE_ROOT.rglob("*.mp4")
        if path.name in SENSORS and len(path.relative_to(SOURCE_ROOT).parts) == 3
    ]
    sources.sort(
        key=lambda p: (
            TASK_ORDER.get(p.relative_to(SOURCE_ROOT).parts[0], 999),
            SCENE_ORDER.get(p.relative_to(SOURCE_ROOT).parts[1], 999),
            SENSORS[p.name]["slug"],
        )
    )
    records = [build_record(path) for path in sources]
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total_mb = sum(r["size_bytes"] for r in records) / 1024 / 1024
    print(f"records={len(records)}")
    print(f"manifest={MANIFEST_PATH}")
    print(f"total_clip_size_mb={total_mb:.2f}")


if __name__ == "__main__":
    main()
