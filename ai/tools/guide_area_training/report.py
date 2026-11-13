"""영상별·부위별 사진 수와 학습·검증 나눔을 모아 summary.json과 표로 낸다(개발용).

judge_frames.py가 만든 photo_counts.json을 읽는다. 나눔은 plan.split_videos 규칙이고,
시험 영상(videos.json의 testVideoId)이 후보에 들어 있으면 멈춘다.
영상마다 단계별 직전·직후 대표 사진을 붙인 그림(sheet.jpg)도 만든다.
실행 (ai/ 폴더에서): uv run --no-sync python tools/guide_area_training/report.py
"""

from collections import Counter

import plan
import workspace
from PIL import Image, ImageDraw

THUMB = (320, 180)
PARTS = plan.ANALYZED_MAKEUPS


def video_row(video: dict, split: str) -> dict | None:
    """영상 하나의 요약 줄. 아직 판정하지 않은 영상은 None이다."""
    video_id = video["videoId"]
    if not workspace.counts_path(video_id).is_file():
        return None
    info = workspace.read_json(workspace.info_path(video_id))
    counts = workspace.read_json(workspace.counts_path(video_id))
    manifest = workspace.read_json(workspace.sample_dir(video_id) / "manifest.json")
    parts = {}
    for part in PARTS:
        groups = [group for group in counts["groups"] if group["makeup"] == part]
        by_step: dict[str, dict[str, dict]] = {}
        for group in groups:
            by_step.setdefault(group["stepId"], {})[group["group"]] = group
        parts[part] = {
            "steps": len(by_step),
            "stepsWithBoth": sum(
                all(pair[name]["usable"] > 0 for name in ("before", "after"))
                for pair in by_step.values()
            ),
            "photos": sum(group["inRange"] for group in groups),
            "usable": sum(group["usable"] for group in groups),
            "picked": sum(len(group["pickedFrames"]) for group in groups),
        }
    frames_dir = workspace.sample_dir(video_id) / "frames"
    return {
        "videoId": video_id,
        "url": video["url"],
        "channel": info["channel"],
        "channelId": info["channel_id"],
        "title": info["title"],
        "license": info["license"],
        "durationSeconds": manifest["source"]["durationSeconds"],
        "fps": manifest["source"]["fps"],
        "split": split,
        "occlusionSplit": video.get("occlusionSplit"),
        "steps": len(manifest["steps"]),
        "stepMakeups": dict(Counter(step["makeup"] for step in manifest["steps"])),
        "photos": counts["photos"],
        "photoBytes": sum(path.stat().st_size for path in frames_dir.glob("*.jpg")),
        "status": counts["status"],
        "parts": parts,
    }


def draw_sheet(video_id: str) -> None:
    """단계마다 직전 묶음의 마지막 고른 사진과 직후 묶음의 첫 고른 사진을 나란히 붙인다."""
    counts = workspace.read_json(workspace.counts_path(video_id))
    frames_dir = workspace.sample_dir(video_id) / "frames"
    by_step: dict[str, dict[str, dict]] = {}
    for group in counts["groups"]:
        by_step.setdefault(group["stepId"], {})[group["group"]] = group
    if not by_step:
        return
    width, height = THUMB
    sheet = Image.new("RGB", (width * 2, (height + 20) * len(by_step)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (step_id, pair) in enumerate(by_step.items()):
        top = index * (height + 20)
        draw.text(
            (4, top + 4), f"{step_id} {pair['before']['makeup']}  before | after", fill="black"
        )
        for column, (name, pick) in enumerate((("before", -1), ("after", 0))):
            picked = pair[name]["pickedFrames"]
            if not picked:
                continue
            with Image.open(frames_dir / f"{picked[pick]:06d}.jpg") as photo:
                sheet.paste(photo.resize(THUMB), (column * width, top + 20))
    sheet.save(workspace.video_dir(video_id) / "sheet.jpg", quality=85)


def table(rows: list[dict]) -> str:
    """영상별·부위별 사진 수 마크다운 표. 칸은 단계 수 / 쓸 사진 / 고른 사진이다."""
    head = "| 영상 | 나눔 | 단계 | 받은 사진 | " + " | ".join(PARTS) + " |"
    line = "|---|---|---|---|" + "---|" * len(PARTS)
    body = [
        f"| `{row['videoId']}` | {row['split']} | {row['steps']} | {row['photos']} | "
        + " | ".join("{steps} / {usable} / {picked}".format(**row["parts"][part]) for part in PARTS)
        + " |"
        for row in rows
    ]
    return "\n".join([head, line, *body])


def main() -> None:
    config = workspace.read_json(workspace.VIDEOS_FILE)
    videos = config["videos"]
    if any(video["videoId"] == config["testVideoId"] for video in videos):
        raise SystemExit("시험 영상이 후보 목록에 들어 있습니다")
    if len({video["videoId"] for video in videos}) != len(videos):
        raise SystemExit("같은 영상 ID가 두 번 들어 있습니다")
    channels = {
        video["videoId"]: workspace.read_json(workspace.info_path(video["videoId"]))["channel_id"]
        for video in videos
    }
    split = plan.split_videos(videos, channels)
    rows = [row for video in videos if (row := video_row(video, split[video["videoId"]]))]
    for row in rows:
        draw_sheet(row["videoId"])
    totals = {
        name: {
            part: {
                key: sum(row["parts"][part][key] for row in rows if row["split"] == name)
                for key in ("steps", "stepsWithBoth", "photos", "usable", "picked")
            }
            for part in PARTS
        }
        for name in ("train", "validation")
    }
    workspace.write_json(
        workspace.SUMMARY_FILE,
        {"testVideoId": config["testVideoId"], "videos": rows, "totals": totals},
    )
    print(table(rows))
    for name, parts in totals.items():
        print(
            f"{name}: "
            + ", ".join(
                f"{part} {value['steps']}단계·{value['usable']}장·{value['picked']}장"
                for part, value in parts.items()
            )
        )
    print(f"저장: {workspace.SUMMARY_FILE}")


if __name__ == "__main__":
    main()
