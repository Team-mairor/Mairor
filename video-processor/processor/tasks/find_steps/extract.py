"""영상을 직접 보고 단계를 뽑는다. 음성만 들으면 말 안 한 동작을 놓치고 시각이 말한 시각이 되기 때문이다.

낮은 해상도 영상과 원음을 따로 받아 조각으로 자르고 조각마다 GMS에 묻는다(clips.py).
- 설명란 장 나눔이 있으면 이어진 장을 묶어 10번 이하로 묻고, 질문에 장 경계와 이름을 적는다. 장 경계는 단계가
  넘지 않게 한다(단계마다 가장 많이 겹치는 장에 넣고 그 장 밖은 자른다).
- 장 나눔이 없으면 6분을 넘지 않는 같은 길이로 나눈다.
조각은 다시 압축하지 않고 그냥 잘라 붙인다. 그렇게 자른 조각은 키프레임에서만 시작할 수 있어 맡은 구간 바로 앞
키프레임부터 자르고, 겹친 앞부분의 단계는 맡은 조각에만 남긴다. 호출이 한꺼번에 몰리지 않게 GMS 클라이언트가
시작 간격과 동시 개수를 조절한다(clients/gms.py).
'낮음' 해상도로 물어 빠르게 받고, 같은 말을 되풀이하다 출력 한도에 닿거나 시각이 조각을 벗어난 답은
기본 해상도로 한 번 더 묻는다. 그래도 틀리면 실행을 멈춘다(틀린 시각으로 단계를 만들지 않는다).
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from processor.clients.gms import DEFAULT_MODEL
from processor.clients.youtube import download
from processor.tasks.find_steps.answers import to_steps
from processor.tasks.find_steps.ask import ask_clip
from processor.tasks.find_steps.clips import cut_clip, keyframe_times, plan_clips, snap_clips
from processor.tasks.find_steps.clock import clock
from processor.tasks.find_steps.step_rules import (
    absorb_aid_tools, absorb_blending, assign_chapters, drop_tool_names, fit_ends, keep_inside, merge_same_product,
)


logger = logging.getLogger("VideoProcessor")

LOWRES_VIDEO = "bv[height<=360][vcodec^=avc1]/bv[height<=360]/wv"
ORIGINAL_AUDIO = "wa[ext=m4a][format_note*=original]/wa[ext=m4a]/ba"


def chapter_marks(clip: dict) -> list[tuple[float, float, str | None]]:
    """조각 안의 장 경계를 조각 기준 시각으로. 조각 00:00은 맡은 구간 바로 앞 키프레임이다."""
    return [(max(c["start"], clip["keepFrom"]) - clip["start"], min(c["end"], clip["keepTo"]) - clip["start"], c["title"])
            for c in clip["chapters"]]


def extract_steps(url: str, work_dir: Path, *, api_key, model=DEFAULT_MODEL, recorder=None,
                  low_first=True, on_download=None) -> dict:
    """낮은 해상도 영상·원음 받기 → 조각(장 또는 같은 길이) → 조각별 GMS 호출 → 맡은 구간만 남기기 → 같은 제품 묶기.

    on_download(낮은 해상도 영상, 원음, 길이)는 받자마자 부른다. 단계와 상관없는 일(제품 글자 위치 찾기, 말 받아쓰기)을
    이때 시작한다.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        video_future = pool.submit(download, url, LOWRES_VIDEO, work_dir, "lowres_video")
        audio_future = pool.submit(download, url, ORIGINAL_AUDIO, work_dir, "original_audio")
        (video, info), (audio, _) = video_future.result(), audio_future.result()
    downloaded = time.perf_counter() - started
    duration = float(info["duration"])
    if on_download:
        on_download(video, audio, duration)
    clips = snap_clips(plan_clips(duration, info.get("chapters")), keyframe_times(video))
    with ThreadPoolExecutor(max_workers=min(8, len(clips))) as pool:
        paths = list(pool.map(
            lambda item: cut_clip(video, audio, item[1]["start"], item[1]["end"], work_dir / f"clip{item[0]}.mp4"),
            enumerate(clips),
        ))
    cut = time.perf_counter() - started - downloaded
    with ThreadPoolExecutor(max_workers=len(clips)) as pool:
        answers = list(pool.map(
            lambda item: ask_clip(item[0], item[1][1], item[1][0]["end"] - item[1][0]["start"],
                                  api_key=api_key, model=model, recorder=recorder, low_first=low_first,
                                  chapters=chapter_marks(item[1][0])),
            enumerate(zip(clips, paths)),
        ))
    asked = time.perf_counter() - started - downloaded - cut
    steps = [
        step
        for index, ((rows, _report), clip) in enumerate(zip(answers, clips))
        for step in assign_chapters(keep_inside(to_steps(rows, clip["start"], index), clip["keepFrom"], clip["keepTo"]),
                                    clip["chapters"])
    ]
    merged = fit_ends(merge_same_product(absorb_aid_tools(drop_tool_names(absorb_blending(steps)))))
    report = {
        "lowresVideo": str(video), "durationSeconds": duration, "chapters": len(info.get("chapters") or []),
        "clips": [{"range": f"{clock(c['start'])}~{clock(c['end'])}", "chapters": [h["title"] for h in c["chapters"]]} | r
                  for c, (_, r) in zip(clips, answers)],
        "downloadSeconds": round(downloaded, 1), "cutSeconds": round(cut, 1), "gmsSeconds": round(asked, 1),
        "rawSteps": len(steps), "steps": len(merged), "clipBytes": [p.stat().st_size for p in paths],
    }
    (work_dir / "video_steps.json").write_text(
        json.dumps({"report": report, "steps": merged}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("[Video steps] 받기 %.1fs 자르기 %.1fs GMS %.1fs 조각 %d개 단계 %d→%d개",
                downloaded, cut, asked, len(clips), len(steps), len(merged))
    return {"steps": merged, "lowresVideo": video, "report": report}
