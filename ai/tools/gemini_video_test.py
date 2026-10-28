"""Gemini 영상 시험 (개발용). 유튜브 영상을 Gemini에 넣어 단계 목록·세부 칸·대표 장면 시각을 받는다.

서비스에서는 BE가 GMS로 Gemini를 부르고 프롬프트도 BE가 관리한다. 여기 프롬프트는 AI 입력 형식
(docs/GUIDE_INPUT.md)을 정하려고 쓴 시험용이다.

실행 (ai/ 폴더에서, .env에 GEMINI_API_KEY 필요):
  uv run python tools/gemini_video_test.py run <유튜브 URL>             결과 → tools/gemini_runs/
  uv run python tools/gemini_video_test.py sample <결과 파일> <저장 경로>  결과 → 가이드 입력 샘플
결과 보기: uv run streamlit run tools/gemini_viewer.py
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import ENV_FILE
from app.schemas.guide import GuideInput

RUNS_DIR = Path(__file__).resolve().parent / "gemini_runs"
# 시각을 초 숫자로 달라고 하면 322(=3분 22초)처럼 분초 숫자로 답해서 MM:SS 문자열로 받는다
PROMPT = (Path(__file__).resolve().parent / "gemini_prompt.txt").read_text(encoding="utf-8")
DEFAULT_MODEL = "gemini-2.5-flash"  # GMS와 같은 모델
# 샘플의 이미지 주소. 실제 주소는 BE가 저장소에 올리고 정한다
SAMPLE_IMAGE_BASE = "https://storage.example.com/guides"

FACT = {
    "type": "OBJECT",
    "nullable": True,
    "properties": {
        "value": {"type": "STRING"},
        "source": {"type": "STRING", "enum": ["voice", "onscreenText", "scene", "estimated"]},
        "at": {"type": "STRING", "nullable": True},
    },
    "required": ["value", "source"],
}

# Gemini가 이 모양의 JSON으로만 답하게 강제한다
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "duration": {"type": "STRING"},
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "order": {"type": "INTEGER"},
                    "makeup": {
                        "type": "STRING",
                        "enum": [
                            "foundation",
                            "eyeshadow",
                            "eyeliner",
                            "blush",
                            "lip",
                            "brow",
                            "mascara",
                            "contour",
                            "highlight",
                            "other",
                        ],
                    },
                    "partLabel": {"type": "STRING"},
                    "startTime": {"type": "STRING"},
                    "endTime": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "product": {
                        "type": "OBJECT",
                        "nullable": True,
                        "properties": {
                            "brand": {"type": "STRING", "nullable": True},
                            "name": {"type": "STRING", "nullable": True},
                            "shade": {"type": "STRING", "nullable": True},
                            "source": {
                                "type": "STRING",
                                "enum": ["voice", "onscreenText", "scene", "estimated"],
                            },
                        },
                    },
                    "facts": {
                        "type": "OBJECT",
                        "properties": {
                            "tool": FACT,
                            "amount": FACT,
                            "strength": FACT,
                            "tips": {"type": "ARRAY", "items": FACT},
                            "cautions": {"type": "ARRAY", "items": FACT},
                            "finishCue": FACT,
                        },
                    },
                    "keyframeTimes": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": [
                    "order",
                    "makeup",
                    "partLabel",
                    "startTime",
                    "endTime",
                    "summary",
                    "facts",
                    "keyframeTimes",
                ],
            },
        },
    },
    "required": ["duration", "steps"],
}


class KeySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = Field(min_length=1)


def video_id_of(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname == "youtu.be":
        return parsed.path.lstrip("/")
    return parse_qs(parsed.query)["v"][0]


def parse_time(value: str | float | None) -> tuple[float | None, str | None]:
    """Gemini가 준 시각 → (초, 문제). 숫자는 시각을 초로 달라고 했던 1회차처럼 분초 숫자로 본다."""
    if value is None:
        return None, None
    if isinstance(value, int | float):
        minutes, seconds = divmod(int(round(value)), 100)
        return minutes * 60 + seconds, (f"{value:g}: 초 자리가 60 이상" if seconds >= 60 else None)
    try:
        parts = [int(p) for p in value.split(":")]
    except ValueError:
        return None, f"{value}: MM:SS 형식이 아님"
    total = 0
    for part in parts:
        total = total * 60 + part
    return total, (f"{value}: 초 자리가 60 이상" if parts[-1] >= 60 else None)


def seconds(value: str | float | None) -> float | None:
    return parse_time(value)[0]


def to_fact(raw: dict) -> dict:
    fact = {"value": raw["value"], "source": raw["source"]}
    if raw.get("at") is not None:
        fact["at"] = seconds(raw["at"])
    return fact


def to_guide_input(run: dict, duration: float | None = None) -> dict:
    """Gemini 결과 → AI 서버 입력 (BE가 할 변환). 대표 장면 시각은 예시 이미지 주소로 바꾼다.

    duration을 안 주면 Gemini가 말한 영상 길이를 쓴다. 실제로는 BE가 유튜브에서 받은 길이를 쓴다.
    """
    output = run["output"]
    video_id = video_id_of(run["videoUrl"])
    image_base = f"{SAMPLE_IMAGE_BASE}/{video_id}"
    steps = []
    for raw in output["steps"]:
        step_id = f"s{raw['order']}"
        facts = {key: None for key in ("tool", "amount", "strength", "finishCue")}
        facts |= {"tips": [], "cautions": []}
        for key, value in (raw.get("facts") or {}).items():
            if isinstance(value, list):
                facts[key] = [to_fact(item) for item in value]
            elif value is not None:
                facts[key] = to_fact(value)
        product = raw.get("product")
        steps.append(
            {
                "stepId": step_id,
                "order": raw["order"],
                "startSeconds": seconds(raw.get("startTime", raw.get("startSeconds"))),
                "endSeconds": seconds(raw.get("endTime", raw.get("endSeconds"))),
                "makeup": raw["makeup"],
                "partLabel": raw["partLabel"],
                "summary": raw["summary"],
                "images": [
                    {"url": f"{image_base}/{step_id}-{i + 1}.jpg", "at": seconds(t)}
                    for i, t in enumerate(raw.get("keyframeTimes", raw.get("keyframeSeconds", [])))
                ],
                "product": (
                    {key: product.get(key) for key in ("brand", "name", "shade")}
                    if product
                    else None
                ),
                "facts": facts,
            }
        )
    duration = duration or seconds(output.get("duration", output.get("durationSeconds")))
    return {"videoId": video_id, "durationSeconds": duration, "steps": steps}


def call_gemini(video_url: str, model: str, key: str) -> dict:
    body = {
        "contents": [{"parts": [{"fileData": {"fileUri": video_url}}, {"text": PROMPT}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "temperature": 0.2,
        },
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e


def next_run_path(video_id: str) -> Path:
    numbers = [int(p.stem.rsplit("_", 1)[1]) for p in RUNS_DIR.glob(f"{video_id}_*.json")]
    return RUNS_DIR / f"{video_id}_{max(numbers, default=0) + 1}.json"


def run(video_url: str, model: str) -> None:
    try:
        key = KeySettings().gemini_api_key
    except ValidationError:
        raise SystemExit("ai/.env에 GEMINI_API_KEY를 넣으세요") from None

    started = time.time()
    raw = call_gemini(video_url, model, key)
    elapsed = time.time() - started
    candidate = raw["candidates"][0]
    text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
    result = {
        "model": model,
        "videoUrl": video_url,
        "elapsedSeconds": round(elapsed, 1),
        "finishReason": candidate.get("finishReason"),
        "usage": raw.get("usageMetadata"),
        "prompt": PROMPT,
        "schema": SCHEMA,
        "output": json.loads(text),
    }
    path = next_run_path(video_id_of(video_url))
    RUNS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {path.relative_to(AI_ROOT)} ({elapsed:.0f}초)")


def sample(run_path: Path, out_path: Path, duration: float | None) -> None:
    run_result = json.loads(run_path.read_text(encoding="utf-8"))
    guide_input = to_guide_input(run_result, duration)
    try:
        GuideInput.model_validate(guide_input)
    except ValidationError as e:
        raise SystemExit(f"입력 검사에서 거절됨:\n{e}") from e
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(guide_input, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"저장: {out_path} (단계 {len(guide_input['steps'])}개)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Gemini 호출 → tools/gemini_runs/에 저장")
    run_parser.add_argument("video_url")
    run_parser.add_argument("--model", default=DEFAULT_MODEL)
    sample_parser = commands.add_parser("sample", help="시험 결과 → 가이드 입력 샘플")
    sample_parser.add_argument("run_path", type=Path)
    sample_parser.add_argument("out_path", type=Path)
    sample_parser.add_argument("--duration", type=float, help="실제 영상 길이(초)")
    args = parser.parse_args()

    if args.command == "run":
        run(args.video_url, args.model)
    else:
        sample(args.run_path, args.out_path, args.duration)


if __name__ == "__main__":
    main()
