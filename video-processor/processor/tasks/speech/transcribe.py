"""원음을 GMS로 받아 적는다. 단계마다 그 단계에서 한 말을 붙여 AI 설명 입력으로 넘기기 위해서다.

- 유튜브 자동 자막보다 정확하다. OubRDaaWGPc의 올린 자막을 정답으로 5분 두 구간을 재면 글자 틀림이 GMS 3.1·5.1%,
  자동 자막 8.5·6.9%였고, 자동 자막은 제품 이름을 틀리고("에스네이처"→"네이처가이") 구절을 통째로 빠뜨렸다.
- 단계 찾기 질문에 칸을 늘려 같이 받으면 단계 경계가 흔들려(정답표 19/19 → 17~18/19) 따로 묻는다.
- 원음을 CLIP_SECONDS를 넘지 않는 같은 길이로 잘라(31분 영상 6조각) 조각마다 한 번 묻고, 말마다 시작 시각(MM:SS)을 받는다.
- 시각이 조각을 벗어나거나 형식이 틀리면 한 번 더 묻는다. 그래도 안 되거나 GMS가 끝내 받아 주지 않으면 그 조각은
  비운다. 말이 없어도 단계와 설명은 만들 수 있다.
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
from processor.schemas.gms_answers import SPEECH_LINES
from processor.tasks.find_steps.clips import even_parts
from processor.tasks.find_steps.clock import clock, parse_clock

ANSWER_ATTEMPTS = 2
ANSWER_TOKENS = 8192

logger = logging.getLogger("VideoProcessor")

PROMPT = (PROMPTS_DIR / "speech.txt").read_text(encoding="utf-8")


def audio_part(audio: Path, start: float, end: float) -> bytes:
    """원음 [start, end]를 모노 mp3로. 소리는 다시 압축해도 빨라서 키프레임에 맞추지 않고 정확한 시각에서 자른다."""
    return subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
         "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(audio),
         "-vn", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "48k", "-f", "mp3", "pipe:1"],
        capture_output=True, check=True, timeout=120,
    ).stdout


def transcribe_part(index: int, audio: Path, start: float, end: float, *, api_key, model=DEFAULT_MODEL,
                    recorder=None) -> list[dict]:
    """조각 하나를 받아 적어 영상 기준 시각의 말 목록 [{at, text}]으로. 끝내 못 받으면 빈 목록이다."""
    length = end - start
    try:
        data = base64.b64encode(audio_part(audio, start, end)).decode()
        for attempt in range(ANSWER_ATTEMPTS):
            raw = generate_content(
                [{"inlineData": {"mimeType": "audio/mp3", "data": data}},
                 {"text": PROMPT.replace("{length}", clock(length))}],
                SPEECH_LINES, model=model, api_key=api_key, phase="speech",
                call_id=f"speech{index}" if attempt == 0 else f"speech{index}-retry",
                recorder=recorder, timeout=300, generation_config={"maxOutputTokens": ANSWER_TOKENS},
            )
            try:
                rows = response_json(raw)["lines"]
                times = [parse_clock(row["at"]) for row in rows]
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            if all(0 <= t <= length + 1 for t in times):
                return [{"at": round(start + t, 1), "text": " ".join(row["text"].split())}
                        for t, row in zip(times, rows) if row["text"].strip()]
    except (RateLimitBudgetExceeded, OSError, ValueError, subprocess.SubprocessError) as error:
        logger.warning("[Speech %d] 받아쓰기 실패로 비움: %s", index, type(error).__name__)
        return []
    logger.warning("[Speech %d] 답 형식이나 시각이 계속 틀려 비움", index)
    return []


def transcribe(audio: Path, duration: float, *, api_key, model=DEFAULT_MODEL, recorder=None, output_dir) -> list[dict]:
    """원음 전체를 받아 적어 시각 순서의 말 목록을 돌려주고 output_dir/speech.json에 남긴다."""
    parts = even_parts(0.0, duration)
    with ThreadPoolExecutor(max_workers=len(parts)) as pool:
        found = list(pool.map(
            lambda item: transcribe_part(item[0], audio, *item[1], api_key=api_key, model=model, recorder=recorder),
            enumerate(parts),
        ))
    lines = sorted((line for part in found for line in part), key=lambda line: line["at"])
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "speech.json").write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[Speech] 조각 %d개, 말 %d줄 (빈 조각 %d개)", len(parts), len(lines), sum(1 for part in found if not part))
    return lines
