#!/usr/bin/env python3
"""Apply automatic face mosaic to gallery MP4 clips.

This is a privacy pass for the anonymous MILD project page. It uses OpenCV Haar
face detectors on every frame, enlarges each detected face region, and replaces
the region with a coarse pixel mosaic. The script overwrites only files that
receive at least one detected face mosaic and regenerates their poster frame.
"""

from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


SITE_ROOT = Path(__file__).resolve().parents[1]
VIDEO_ROOT = SITE_ROOT / "assets" / "videos" / "gallery"
POSTER_ROOT = SITE_ROOT / "assets" / "posters" / "gallery"
MANIFEST_PATH = SITE_ROOT / "assets" / "videos" / "gallery_manifest.json"
REPORT_PATH = SITE_ROOT / "assets" / "videos" / "gallery_face_mosaic_report.csv"
TMP_ROOT = SITE_ROOT / "assets" / "videos" / "_mosaic_tmp"
DETECT_STRIDE = 4
BOX_HOLD_FRAMES = 7


@dataclass
class ClipReport:
    video: str
    frames: int
    frames_with_faces: int
    detections: int
    changed: bool


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def load_detector(filename: str) -> cv2.CascadeClassifier:
    path = Path(cv2.data.haarcascades) / filename
    detector = cv2.CascadeClassifier(str(path))
    if detector.empty():
      raise RuntimeError(f"Failed to load Haar cascade: {path}")
    return detector


FRONTAL = [
    load_detector("haarcascade_frontalface_default.xml"),
    load_detector("haarcascade_frontalface_alt2.xml"),
]
PROFILE = load_detector("haarcascade_profileface.xml")


def intersect_over_union(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def merge_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    for box in boxes:
        keep = True
        for i, old in enumerate(merged):
            if intersect_over_union(box, old) > 0.28:
                x1 = min(box[0], old[0])
                y1 = min(box[1], old[1])
                x2 = max(box[0] + box[2], old[0] + old[2])
                y2 = max(box[1] + box[3], old[1] + old[3])
                merged[i] = (x1, y1, x2 - x1, y2 - y1)
                keep = False
                break
        if keep:
            merged.append(box)
    return merged


def expand_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x, y, w, h = box
    cx = x + w / 2
    cy = y + h / 2
    side_w = w * 1.9
    side_h = h * 2.15
    x1 = max(0, int(cx - side_w / 2))
    y1 = max(0, int(cy - side_h * 0.52))
    x2 = min(width, int(cx + side_w / 2))
    y2 = min(height, int(cy + side_h * 0.48))
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


def detect_faces(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    height, width = frame.shape[:2]
    max_width = 760
    scale = min(1.0, max_width / width)
    if scale < 1.0:
        small = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    else:
        small = frame

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    boxes: list[tuple[int, int, int, int]] = []

    for detector in FRONTAL:
        found = detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(18, 18))
        boxes.extend(tuple(map(int, box)) for box in found)

    profile = PROFILE.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(18, 18))
    boxes.extend(tuple(map(int, box)) for box in profile)

    flipped = cv2.flip(gray, 1)
    profile_flipped = PROFILE.detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=4, minSize=(18, 18))
    for x, y, w, h in profile_flipped:
        boxes.append((gray.shape[1] - int(x) - int(w), int(y), int(w), int(h)))

    if scale < 1.0:
        inv = 1.0 / scale
        boxes = [(int(x * inv), int(y * inv), int(w * inv), int(h * inv)) for x, y, w, h in boxes]

    boxes = [expand_box(box, width, height) for box in boxes]
    return merge_boxes(boxes)


def mosaic(frame: np.ndarray, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    roi = frame[y : y + h, x : x + w]
    if roi.size == 0:
        return
    block = max(8, min(w, h) // 7)
    small_w = max(1, w // block)
    small_h = max(1, h // block)
    small = cv2.resize(roi, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
    pixelated = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    frame[y : y + h, x : x + w] = pixelated


def regenerate_poster(video_path: Path, poster_path: Path) -> None:
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "1.0",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "4",
            str(poster_path),
        ]
    )


def process_video(video_path: Path, poster_path: Path) -> ClipReport:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Failed to open {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    tmp_path = TMP_ROOT / video_path.name
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{width}x{height}",
            "-r",
            f"{fps:.6f}",
            "-i",
            "-",
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
            str(tmp_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    frames = 0
    frames_with_faces = 0
    detections = 0
    last_boxes: list[tuple[tuple[int, int, int, int], int]] = []
    changed = False

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        boxes = detect_faces(frame) if frames % DETECT_STRIDE == 0 else []
        last_boxes = [(box, age + 1) for box, age in last_boxes if age < BOX_HOLD_FRAMES]
        if boxes:
            last_boxes = [(box, 0) for box in boxes]
        active_boxes = merge_boxes([box for box, _ in last_boxes])
        if active_boxes:
            frames_with_faces += 1
            detections += len(active_boxes)
            changed = True
            for box in active_boxes:
                mosaic(frame, box)
        assert ffmpeg.stdin is not None
        ffmpeg.stdin.write(frame.tobytes())
        frames += 1

    capture.release()
    assert ffmpeg.stdin is not None
    ffmpeg.stdin.close()
    ffmpeg.stdin = None
    _, stderr = ffmpeg.communicate()
    if ffmpeg.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {video_path}: {stderr.decode(errors='replace')[-2000:]}")

    if changed:
        tmp_path.replace(video_path)
        regenerate_poster(video_path, poster_path)
    else:
        tmp_path.unlink(missing_ok=True)

    return ClipReport(
        video=str(video_path.relative_to(SITE_ROOT)),
        frames=frames,
        frames_with_faces=frames_with_faces,
        detections=detections,
        changed=changed,
    )


def main() -> None:
    records = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    reports: list[ClipReport] = []
    for index, record in enumerate(records, start=1):
        video_path = SITE_ROOT / record["video"]
        poster_path = SITE_ROOT / record["poster"]
        report = process_video(video_path, poster_path)
        if video_path.exists():
            record["size_bytes"] = video_path.stat().st_size
        record["privacy_filter"] = "opencv-haar-face-mosaic-v1" if report.changed else "opencv-haar-face-scan-no-detection"
        reports.append(report)
        print(
            f"[{index:03d}/{len(records):03d}] changed={report.changed} "
            f"frames_with_faces={report.frames_with_faces} detections={report.detections} {report.video}",
            flush=True,
        )

    MANIFEST_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with REPORT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["video", "frames", "frames_with_faces", "detections", "changed"])
        writer.writeheader()
        for report in reports:
            writer.writerow(report.__dict__)

    changed_count = sum(1 for report in reports if report.changed)
    frames_with_faces = sum(report.frames_with_faces for report in reports)
    detections = sum(report.detections for report in reports)
    print(f"changed_videos={changed_count}")
    print(f"frames_with_faces={frames_with_faces}")
    print(f"detections={detections}")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
