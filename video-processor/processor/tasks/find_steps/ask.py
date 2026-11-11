"""영상 조각을 GMS에 보여 주고 단계 목록을 받는다. 답이 틀리면 다시 묻는다."""

import base64
import logging
import time
from pathlib import Path

from processor.clients.gms import DEFAULT_MODEL, generate_content, response_json
from processor.core.paths import PROMPTS_DIR
from processor.schemas.gms_answers import STEP_LIST
from processor.tasks.find_steps.clock import clock, parse_clock


logger = logging.getLogger("VideoProcessor")

ANSWER_TOKENS = 8192
PROMPT = (PROMPTS_DIR / "find_steps.txt").read_text(encoding="utf-8")
CHAPTER_PROMPT = (PROMPTS_DIR / "find_steps_chapter.txt").read_text(encoding="utf-8")


def answer_problem(raw: dict, length: float) -> tuple[str | None, list[dict]]:
    """조각 답이 쓸 만한지 본다. 출력 한도에 닿았거나, 시각이 조각을 벗어나거나, 끝이 시작보다 앞서면 문제다."""
    candidate = (raw.get("candidates") or [{}])[0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        return "출력 한도에 닿음", []
    try:
        rows = response_json(raw)["steps"]
        for row in rows:
            for item in [row, *row.get("pieces", [])]:
                first, last = parse_clock(item["firstTouch"]), parse_clock(item["lastTouch"])
                if not 0 <= first <= last <= length + 1:
                    return f"시각이 조각을 벗어나거나 거꾸로 감: {item['firstTouch']}~{item['lastTouch']}", []
    except (ValueError, KeyError, IndexError, TypeError) as error:
        return f"답 형식 오류 ({type(error).__name__})", []
    return None, rows


def ask_clip(index: int, path: Path, length: float, *, api_key, model=DEFAULT_MODEL, recorder=None,
             low_first=True, chapters: list[tuple[float, float, str | None]] | None = None,
             ) -> tuple[list[dict], dict]:
    """low_first면 '낮음' 해상도로 먼저 묻고, 틀리면 기본 해상도로 한 번 더 묻는다. 아니면 기본으로 두 번까지 묻는다.

    질문에 조각 길이를 적는다. 화면에 진행 시간 타이머를 띄우는 영상에서 모델이 타이머 숫자를 시각으로 써서
    (tSBaf010odM: 5분 36초 조각에 05:37~09:56) 답이 조각을 벗어났다. 길이를 적으니 기본 해상도에서도 재생 시간으로 답했다.
    조각 안의 장 경계(chapters: 조각 기준 시작·끝 초, 장 이름)가 있으면 질문 끝에 적는다.
    """
    data = base64.b64encode(path.read_bytes()).decode()
    marks = "\n".join(f"  - {clock(a)}~{clock(b)} {title or ''}".rstrip() for a, b, title in chapters or [])
    prompt = PROMPT.replace("{length}", clock(length)) + (CHAPTER_PROMPT.replace("{chapters}", marks) if marks else "")
    report = {"clip": index, "attempts": []}
    for attempt, low in enumerate((low_first, False)):
        started = time.perf_counter()
        raw = generate_content(
            [{"inlineData": {"mimeType": "video/mp4", "data": data}},
             {"text": prompt}],
            STEP_LIST, model=model, api_key=api_key, phase="video_steps",
            call_id=f"clip{index}" if attempt == 0 else f"clip{index}-retry",
            recorder=recorder, timeout=300,
            generation_config={"maxOutputTokens": ANSWER_TOKENS}
            | ({"mediaResolution": "MEDIA_RESOLUTION_LOW"} if low else {}),
        )
        problem, rows = answer_problem(raw, length)
        usage = raw.get("usageMetadata", {})
        report["attempts"].append({
            "low": low, "seconds": round(time.perf_counter() - started, 1), "problem": problem,
            "inputTokens": usage.get("promptTokenCount"), "outputTokens": usage.get("candidatesTokenCount"),
        })
        if problem is None:
            return rows, report
        logger.warning("[Video steps clip%d] %s 답이 틀림: %s", index, "낮음" if low else "기본", problem)
    raise ValueError(f"GMS 단계 답이 계속 틀림 (조각 {index}): {problem}")
