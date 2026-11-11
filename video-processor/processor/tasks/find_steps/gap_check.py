"""분석하는 단계의 앞뒤 빈 구간을 화면으로 보고, 그 제품을 아직 바르는 중이면 시작·끝을 바깥쪽으로 넓힌다.

영상으로 뽑은 단계는 바르다가 말하며 멈췄다 다시 바르는 곳에서 끝을 일찍 끊는다
(정답표 #7: 08:59에 끊었지만 09:05에 브러시로 한 번 더 정리). AI는 시작 직전·끝 직후 사진을 비교하므로
그 사진에 이 제품을 바르는 모습이 찍히지 않게 넓히는 쪽만 고친다.
- 빈 구간: 앞 단계 끝 ~ 시작(최대 BEFORE_SPAN초), 끝 ~ 다음 단계 시작(최대 AFTER_SPAN초). 이웃 단계와 장 경계를
  넘지 않는다.
- 장 나눔이 있으면 장의 마지막 단계의 끝 뒤만 본다. 끝을 일찍 끊어 틀린 단계(정답표 #9·#12·#23·#30)는 모두 장의
  마지막 단계였고 장 끝까지 3~14초가 남아 있었다. 같은 장에서 뒤에 다른 단계가 오면 보지 않고, 시작 쪽도 보지 않는다
  (직전 사진은 틀린 적이 없음). 31분 영상에서 분석 단계 19개 중 8개만 묻는다. 장 나눔이 없으면 모든 분석 단계의 앞뒤를 본다.
- 단계마다 따로 묻는다. 단계 여럿(사진 60~80장)을 한 번에 물으면 모델이 사진을 하나씩 보지 않고 단계째로
  답해, 같은 사진인데 실행마다 묶음째 뒤집혔다(같은 사진 218장 중 33장).
- 1080p 가운데 얼굴 부분을 보고 "펜슬·브러시 끝이 피부에 닿아 있나"를 묻는다. 빈 구간은 제품을 들고 말하거나
  가리키는 장면이 많아, 360p 사진으로 "바르는 중인가"를 물으면 들고만 있어도 바른다고 답했다.
- 컨실러는 바른 자리를 넣어 묻는다(자리마다 다른 단계라서).
- 넓히기는 경계에서 MAX_PAUSE초 안에 이어지는 '닿음'까지만 한다. 떨어진 사진 하나로 넓어지지 않는다.
  시작 = 처음 닿은 사진 − STEP, 끝 = 마지막 닿은 사진 + STEP (사진 사이에서 시작·끝났을 수 있어 한 칸 넓힌다).
- 붙은 두 단계가 같은 빈 구간 쪽으로 넓어져 겹치면 앞 단계 끝을 뒤 단계 시작에 맞춘다. 끝 = 다음 시작은 그대로다.
  겹쳤다는 것은 같은 사진에 두 제품 모두 '닿음'이라 답한 것이라 어느 쪽이 맞는지 모른다.
- 사진을 못 뽑거나, 답 형식이 계속 틀리거나, GMS가 끝내 받아 주지 않으면 그 단계는 받은 시각을 둔다.
"""

import base64
import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imageio_ffmpeg

from processor.clients.gms import DEFAULT_MODEL, RateLimitBudgetExceeded, generate_content, response_json
from processor.core.paths import PROMPTS_DIR
from processor.schemas.gms_answers import GAP_FRAMES
from processor.schemas.makeup import KIND_WORDS
from processor.tasks.find_steps.step_rules import fit_ends
from processor.tasks.frames.windows import AI_WINDOWS_MS

STEP = 2.0
BEFORE_SPAN = 12.0
AFTER_SPAN = 26.0
MAX_PAUSE = 6.0
WORKERS = 8
ANSWER_ATTEMPTS = 2

logger = logging.getLogger("VideoProcessor")

PROMPT = (PROMPTS_DIR / "gap_check.txt").read_text(encoding="utf-8")

def gap_plan(steps: list[dict], duration: float) -> list[dict]:
    """분석하는 단계마다 앞뒤 빈 구간의 사진 시각. 빈 구간이 STEP보다 짧은 쪽은 보지 않는다.

    장 나눔이 있으면 장의 마지막 단계만, 끝 뒤만 본다.
    """
    plans = []
    for i, step in enumerate(steps):
        chaptered = step.get("chapterEnd") is not None
        if step.get("makeup") not in AI_WINDOWS_MS or (
                chaptered and any(other.get("chapter") == step.get("chapter") for other in steps[i + 1:])):
            continue
        low = steps[i - 1]["absEnd"] if i else 0.0
        high = steps[i + 1]["absStart"] if i + 1 < len(steps) else duration
        if step.get("chapterStart") is not None:
            low, high = max(low, step["chapterStart"]), min(high, step["chapterEnd"])
        before_low = max(low, step["absStart"] - BEFORE_SPAN)
        after_high = min(high, step["absEnd"] + AFTER_SPAN)
        before, t = [], step["absStart"] - STEP
        while t >= before_low + 0.25 and AI_WINDOWS_MS[step["makeup"]][0] is not None and not chaptered:
            before.insert(0, round(t, 2))
            t -= STEP
        after, t = [], step["absEnd"] + STEP
        while t <= after_high - 0.25:
            after.append(round(t, 2))
            t += STEP
        if before or after:
            plans.append({"index": i, "before": before, "after": after,
                          "low": low, "high": high})
    return plans


def frame_at(video: Path, second: float) -> bytes:
    """가운데 정사각형(가로 영상이면 얼굴 쪽)을 잘라 768로 줄인다. 한 장이 GMS 이미지 한 칸에 들어간다."""
    return subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-threads", "1",
         "-ss", f"{second:.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", "crop='min(iw,ih)':'min(iw,ih)',scale=768:768",
         "-c:v", "mjpeg", "-q:v", "3", "-f", "image2pipe", "pipe:1"],
        capture_output=True, check=True, timeout=60,
    ).stdout


def question(step: dict) -> str:
    kind = KIND_WORDS.get(step.get("productKind") or "", "cosmetic")
    what = f"{step.get('productName') or 'this product'} ({kind})"
    where = ""
    if step.get("productKind") == "concealer":
        areas = ", ".join(dict.fromkeys(e.get("faceArea") for e in step.get("events", []) if e.get("faceArea")))
        where = f" at {areas or step.get('area')} (the same place, not another part of the face)"
    return PROMPT.format(what=what, where=where)


def extend(step: dict, plan: dict, answers: dict) -> dict:
    """경계에서 MAX_PAUSE초 안에 이어지는 '닿음' 사진까지 시작·끝을 넓힌다. 이웃 단계를 넘지 않는다."""
    start, end = step["absStart"], step["absEnd"]
    last, used_after = end, 0
    for t in plan["after"]:
        if t - last > MAX_PAUSE:
            break
        if answers.get(f"a{t}") is True:
            last, used_after = t, used_after + 1
    first, used_before = start, 0
    for t in reversed(plan["before"]):
        if first - t > MAX_PAUSE:
            break
        if answers.get(f"b{t}") is True:
            first, used_before = t, used_before + 1
    new_start = max(plan["low"] + 0.5, first - STEP) if first < start else start
    new_end = min(plan["high"] - 0.5, last + STEP) if last > end else end
    return {"start": round(new_start, 2), "end": round(new_end, 2), "speechStart": start, "speechEnd": end,
            "extendedBefore": used_before, "extendedAfter": used_after}


def ask(step: dict, plan: dict, video: Path, *, api_key, model, recorder, output_dir) -> dict:
    """한 단계의 앞뒤 사진에 '닿음' 답을 받는다. 끝내 형식이 틀리면 빈 답이다."""
    ids = [f"b{t}" for t in plan["before"]] + [f"a{t}" for t in plan["after"]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        images = list(pool.map(lambda frame_id: frame_at(video, float(frame_id[1:])), ids))
    parts = [{"text": question(step)}]
    for frame_id, image in zip(ids, images):
        side = "before the step starts" if frame_id[0] == "b" else "after the step ends"
        parts += [{"text": f"frameId={frame_id} ({side}, {float(frame_id[1:]):.0f}s)"},
                  {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(image).decode()}}]
    schema = json.loads(json.dumps(GAP_FRAMES))
    schema["properties"]["frames"]["items"]["properties"]["frameId"]["enum"] = ids
    answers = {}
    for attempt in range(ANSWER_ATTEMPTS):
        raw = generate_content(parts, schema, model=model, api_key=api_key, phase="gap_check",
                               call_id=f"s{plan['index']}" if attempt == 0 else f"s{plan['index']}-retry",
                               recorder=recorder, timeout=120)
        try:
            rows = response_json(raw)["frames"]
        except (ValueError, KeyError, IndexError):
            continue
        if sorted(r["frameId"] for r in rows) == sorted(ids):
            answers = {r["frameId"]: r["applying"] for r in rows}
            break
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / f"s{plan['index']}.json").write_text(
        json.dumps({"plan": plan, "product": step.get("productName"), "answers": answers},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return answers


def check_gaps(steps: list[dict], video: Path, duration: float, *, api_key, model=DEFAULT_MODEL,
               recorder=None, output_dir) -> list[dict]:
    """빈 구간을 확인해 시작·끝을 넓힌 단계 목록을 돌려준다. 단계마다 gapCheck에 넓힌 내용을 남긴다.

    넓혀서 겹친 이웃 단계는 앞 단계 끝을 뒤 단계 시작에 맞춘다(fit_ends).
    """
    steps = sorted(steps, key=lambda s: (s["absStart"], s["absEnd"]))
    plans = gap_plan(steps, duration)

    def run(plan):
        try:
            return ask(steps[plan["index"]], plan, video, api_key=api_key, model=model, recorder=recorder,
                       output_dir=output_dir)
        except (RateLimitBudgetExceeded, OSError, ValueError, subprocess.SubprocessError) as error:
            logger.warning("[Gap check s%d] 사진·GMS 실패로 받은 시각을 둠: %s", plan["index"],
                           type(error).__name__)
            return {}

    with ThreadPoolExecutor(max_workers=max(1, min(WORKERS, len(plans)))) as pool:
        answers = list(pool.map(run, plans))
    out = [dict(step) for step in steps]
    for plan, answer in zip(plans, answers):
        outcome = extend(steps[plan["index"]], plan, answer)
        out[plan["index"]].update(absStart=outcome["start"], absEnd=outcome["end"], gapCheck=outcome)
    logger.info("[Gap check] 단계 %d개, 넓힘 %d개", len(plans),
                sum(1 for p in plans if out[p["index"]]["gapCheck"]["extendedBefore"]
                    or out[p["index"]]["gapCheck"]["extendedAfter"]))
    return fit_ends(out)
