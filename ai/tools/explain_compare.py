"""단계 설명 모델 비교 (개발용). 단계마다 GMS로 여러 모델을 불러 쉬운 설명을 만들고 검사한다.

S15P31A306-249 모델 결정용 시험이다. 가이드 입력의 단계 글만 보내고 이미지는 보내지 않는다.

실행 (ai/ 폴더에서, .env에 GMS_API_KEY 필요):
  uv run python tools/explain_compare.py                            샘플 local_01, 세 모델 모두
  uv run python tools/explain_compare.py --models claude --steps 1-5
결과 → tools/explain_runs/<영상 ID>_<회차>.json
결과 보기: uv run streamlit run tools/explain_viewer.py
"""

import argparse
import copy
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import ENV_FILE
from app.schemas.guide import GuideInput

TOOLS_DIR = Path(__file__).resolve().parent
RUNS_DIR = TOOLS_DIR / "explain_runs"
PROMPT = (TOOLS_DIR / "explain_prompt.txt").read_text(encoding="utf-8")
# 프롬프트를 고치면 올린다. 실행끼리 비교할 때 본다
# v1: 하는 법·팁·주의·끝내는 기준 칸 / v2: 단계 화면용 동작 목록 + 동작에 붙은 팁
PROMPT_VERSION = "v2"
DEFAULT_SAMPLE = AI_ROOT / "samples" / "local_01" / "guide_input.json"

# GMS는 각 회사 API 주소 앞에 이 주소를 붙여 그대로 전달한다
GMS_BASE = "https://gms.ssafy.io/gmsapi"
# 크레딧을 아끼려고 회사마다 작은 모델을 쓴다
MODELS = {"gpt": "gpt-5.4-mini", "gemini": "gemini-3.5-flash-lite", "claude": "claude-haiku-5-5"}
# 공개 요금 (달러, 100만 토큰당 입력·출력). 생각 토큰은 출력 요금으로 계산된다.
# 예전 실행도 계산할 수 있게 지금 안 쓰는 모델도 남겨 둔다
PRICES = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "claude-haiku-5-5": (0.10, 0.50),
}
# GMS 사이트의 사용량 숫자 = 달러 × 10,000. 10.27 첫 사용량(gemini-3.5-flash 1984, Claude 97)이
# 공개 요금 계산과 같았다. GPT는 공개 요금으로 231인데 사이트는 404여서 GMS 단가를 확인해야 한다
GMS_UNITS_PER_USD = 10_000
TIMEOUT_SECONDS = 120
RETRY_STATUS = {429, 500, 502, 503, 504}
WORKERS = 6
# 근거 시각이 단계 구간을 이만큼 넘어도 그 단계 것으로 본다
MARGIN_SECONDS = 5

# 단계 화면 한 장에 들어갈 양. 개수·글자 수는 응답 형식으로 강제하지 않고 검사에서 거른다
MAX_ACTIONS = 4
MAX_TIPS = 2
MAX_ACTION_CHARS = 25  # 띄어쓰기 포함
MAX_TIP_CHARS = 30

SOURCES = {"type": "array", "items": {"type": "string"}}
SENTENCE = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "sources": SOURCES},
    "required": ["text", "sources"],
    "additionalProperties": False,
}
TIP = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "kind": {"type": "string", "enum": ["tip", "caution"]},
        "sources": SOURCES,
    },
    "required": ["text", "kind", "sources"],
    "additionalProperties": False,
}
ACTION = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "sources": SOURCES,
        "tip": {"anyOf": [TIP, {"type": "null"}]},
    },
    "required": ["text", "sources", "tip"],
    "additionalProperties": False,
}
# 세 회사 모두 이 JSON Schema 모양으로만 답하게 강제한다
SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {"type": "array", "items": ACTION},
        "doneWhen": {"anyOf": [SENTENCE, {"type": "null"}]},
        "unused": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["id", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["actions", "doneWhen", "unused"],
    "additionalProperties": False,
}

# 검사: 입력에 없는 도구, 근거 글과 반대인 방향
TOOL_WORDS = [
    "브러시", "퍼프", "손가락", "스패출러", "면봉",
    "스펀지", "화장솜", "핀셋", "어플리케이터", "펜슬",
]  # fmt: skip
OPPOSITES = [
    ("안쪽", "바깥쪽"), ("위쪽", "아래쪽"), ("위로", "아래로"),
    ("앞쪽", "뒤쪽"), ("안에서", "밖에서"),
]  # fmt: skip
NUMBER = re.compile(r"\d+(?:\.\d+)?")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


class KeySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    gms_api_key: str = Field(min_length=1)


class CallError(Exception):
    """모델 호출 실패. 메시지가 결과 파일의 error가 된다."""


@dataclass(frozen=True)
class Reply:
    text: str
    model_version: str | None
    finish: str | None
    input_tokens: int
    output_tokens: int  # 생각 토큰을 뺀 답 토큰
    thinking_tokens: int


# ---------- 입력 정리 ----------


def move_misplaced(steps: list[dict]) -> tuple[list[dict], list[dict]]:
    """근거 시각이 구간 밖인 팁·주의점을 그 시각이 속한 단계로 옮긴다.

    Gemini가 이웃 단계의 팁을 붙이거나 같은 팁을 두 단계에 복사하는 일이 있어서다.
    옮길 단계에 같은 내용이 있으면 버린다.
    """
    steps = copy.deepcopy(steps)
    log = []
    for step in steps:
        facts = step.get("facts") or {}
        start, end = step["startSeconds"] - MARGIN_SECONDS, step["endSeconds"] + MARGIN_SECONDS
        for field in ("tips", "cautions"):
            keep = []
            for item in facts.get(field, []):
                at = item.get("at")
                inside = at is None or start <= at <= end
                target = (
                    None
                    if inside
                    else next((s for s in steps if s["startSeconds"] <= at < s["endSeconds"]), None)
                )
                if target is None:
                    keep.append(item)
                    continue
                moved_to = target.setdefault("facts", {}).setdefault(field, [])
                duplicate = any(x["value"] == item["value"] for x in moved_to)
                if not duplicate:
                    moved_to.append(item)
                log.append(
                    {
                        "from": step["order"],
                        "to": target["order"],
                        "field": field,
                        "value": item["value"],
                        "at": at,
                        "action": "버림 (같은 내용 있음)" if duplicate else "옮김",
                    }
                )
            if field in facts:
                facts[field] = keep
    return steps, log


def inputs_of(step: dict) -> dict[str, str]:
    """모델에 줄 입력. 번호를 붙여서 모델이 문장마다 근거 번호를 달게 한다."""
    facts = step.get("facts") or {}
    inputs = {"summary": step["summary"]}
    for field in ("tool", "amount", "strength", "finishCue"):
        if facts.get(field):
            inputs[field] = facts[field]["value"]
    for prefix, field in (("t", "tips"), ("c", "cautions")):
        for i, item in enumerate(facts.get(field, []), 1):
            inputs[f"{prefix}{i}"] = item["value"]
    return inputs


def user_message(step: dict, inputs: dict[str, str]) -> str:
    lines = "\n".join(f"{key}: {value}" for key, value in inputs.items())
    return f"단계 이름: {step['partLabel']}\n\n[입력]\n{lines}"


# ---------- 호출 ----------


def post(url: str, body: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code not in RETRY_STATUS or attempt == 2:
                raise CallError(f"HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                raise CallError(f"연결 실패: {e}") from e
        time.sleep(5 * (attempt + 1))
    raise AssertionError("도달하지 않음")


def call_gpt(model: str, system: str, user: str, key: str) -> Reply:
    raw = post(
        f"{GMS_BASE}/api.openai.com/v1/chat/completions",
        {
            "model": model,
            "messages": [
                {"role": "developer", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "step_explanation", "strict": True, "schema": SCHEMA},
            },
        },
        {"Authorization": f"Bearer {key}"},
    )
    choice = raw["choices"][0]
    usage = raw["usage"]
    thinking = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
    return Reply(
        text=choice["message"]["content"] or "",
        model_version=raw.get("model"),
        finish=choice.get("finish_reason"),
        input_tokens=usage["prompt_tokens"],
        output_tokens=usage["completion_tokens"] - thinking,
        thinking_tokens=thinking,
    )


def call_gemini(model: str, system: str, user: str, key: str) -> Reply:
    raw = post(
        f"{GMS_BASE}/generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": SCHEMA,
            },
        },
        {"x-goog-api-key": key},
    )
    candidate = raw["candidates"][0]
    parts = candidate.get("content", {}).get("parts", [])
    usage = raw.get("usageMetadata", {})
    return Reply(
        text="".join(p.get("text", "") for p in parts if not p.get("thought")),
        model_version=raw.get("modelVersion"),
        finish=candidate.get("finishReason"),
        input_tokens=usage.get("promptTokenCount", 0),
        output_tokens=usage.get("candidatesTokenCount", 0),
        thinking_tokens=usage.get("thoughtsTokenCount", 0),
    )


def call_claude(model: str, system: str, user: str, key: str) -> Reply:
    raw = post(
        f"{GMS_BASE}/api.anthropic.com/v1/messages",
        {
            "model": model,
            "max_tokens": 16000,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
        },
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    if raw.get("stop_reason") == "refusal":
        raise CallError(f"거절됨: {raw.get('stop_details')}")
    usage = raw["usage"]
    thinking = (usage.get("output_tokens_details") or {}).get("thinking_tokens", 0)
    return Reply(
        text="".join(block["text"] for block in raw["content"] if block["type"] == "text"),
        model_version=raw.get("model"),
        finish=raw.get("stop_reason"),
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"] - thinking,
        thinking_tokens=thinking,
    )


CALLERS: dict[str, Callable[[str, str, str, str], Reply]] = {
    "gpt": call_gpt,
    "gemini": call_gemini,
    "claude": call_claude,
}


# ---------- 검사 ----------


def sentences_of(output: dict) -> list[tuple[str, dict]]:
    """(어느 칸, 문장). 칸 이름은 확인 화면에 그대로 보여 준다. 프롬프트 v1 결과도 읽는다."""
    if "actions" not in output:  # v1: 하는 법·팁·주의·끝내는 기준 칸
        found = [(f"하는 법 {i}", s) for i, s in enumerate(output["instructions"], 1)]
        found += [("팁", s) for s in output["tips"]]
        found += [("주의", s) for s in output["cautions"]]
        if output.get("finishCue"):
            found.append(("끝내는 기준", output["finishCue"]))
        return found
    found = []
    for i, action in enumerate(output["actions"], 1):
        found.append((f"동작 {i}", action))
        if action["tip"]:
            found.append((f"동작 {i} 팁", action["tip"]))
    if output["doneWhen"]:
        found.append(("넘어갈 때", output["doneWhen"]))
    return found


def check(output: dict, inputs: dict[str, str], product: dict | None) -> list[dict]:
    """코드로 잡을 수 있는 문제만 본다. 뜻이 바뀐 문장은 사람이 화면에서 본다."""
    problems = []
    every_input = " ".join(inputs.values())
    names = [value for value in (product or {}).values() if value]
    main_tool = inputs.get("tool", "")
    # 입력에 다른 도구가 나오면 단계 중간에 도구를 바꾸는 단계라 도구 이름을 써도 된다
    changes_tool = any(w in every_input and w not in main_tool for w in TOOL_WORDS)

    actions = output["actions"]
    tips = [action["tip"] for action in actions if action["tip"]]
    if not 1 <= len(actions) <= MAX_ACTIONS:
        detail = f"동작 {len(actions)}개 (1~{MAX_ACTIONS}개)"
        problems.append({"kind": "개수", "where": "동작", "text": "", "detail": detail})
    if len(tips) > MAX_TIPS:
        detail = f"팁 {len(tips)}개 (최대 {MAX_TIPS}개)"
        problems.append({"kind": "개수", "where": "팁", "text": "", "detail": detail})

    for where, sentence in sentences_of(output):
        text, sources = sentence["text"], sentence["sources"]
        cited = " ".join(inputs.get(s, "") for s in sources)
        is_action = where.startswith("동작") and not where.endswith("팁")
        limit = MAX_ACTION_CHARS if is_action else MAX_TIP_CHARS

        def add(kind: str, detail: str, where: str = where, text: str = text) -> None:
            problems.append({"kind": kind, "where": where, "text": text, "detail": detail})

        if len(text) > limit:
            add("길이", f"{len(text)}자 (최대 {limit}자)")
        # 단계 도구는 화면에 따로 보인다. '손'처럼 한 글자는 다른 말(손바닥)에 섞여 있어 보지 않는다
        if len(main_tool) > 1 and main_tool in text and not changes_tool:
            add("도구 이름", f"단계 도구 '{main_tool}'를 문장에 씀")
        if not sources:
            add("근거", "근거 번호가 없음")
        unknown = [s for s in sources if s not in inputs]
        if unknown:
            add("근거", f"입력에 없는 번호 {unknown}")
        for number in NUMBER.findall(text):
            if number not in cited:
                add("숫자", f"'{number}'이(가) 근거 글에 없음")
        for name in names:
            if name in text:
                add("제품 이름", f"'{name}'")
        for tool in TOOL_WORDS:
            if tool in text and tool not in every_input:
                add("도구", f"입력에 없는 도구 '{tool}'")
        for a, b in OPPOSITES:
            for word, opposite in ((a, b), (b, a)):
                if word in text and opposite in cited and word not in cited:
                    add("방향", f"문장은 '{word}', 근거 글은 '{opposite}'")
        for piece in SENTENCE_BREAK.split(text.strip()):
            piece = piece.rstrip(" .!?")
            if piece and not piece.endswith("요"):
                add("말투", f"해요체 아님: …{piece[-8:]}")
    return problems


# ---------- 실행 ----------


def run_one(provider: str, step: dict, key: str) -> dict:
    inputs = inputs_of(step)
    record = {"provider": provider, "model": MODELS[provider], "stepId": step["stepId"]}
    started = time.time()
    try:
        reply = CALLERS[provider](MODELS[provider], PROMPT, user_message(step, inputs), key)
        record.update(
            modelVersion=reply.model_version,
            finish=reply.finish,
            tokens={
                "input": reply.input_tokens,
                "output": reply.output_tokens,
                "thinking": reply.thinking_tokens,
            },
        )
        output = json.loads(reply.text)
        problems = check(output, inputs, step.get("product"))
        record.update(output=output, problems=problems, error=None)
    except CallError as e:
        record.update(output=None, problems=[], error=str(e))
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        record.update(output=None, problems=[], error=f"응답 형식이 틀림: {e!r}")
    record["seconds"] = round(time.time() - started, 1)
    return record


def gms_usage(model: str, tokens: dict | None, prices: dict | None = None) -> float:
    """호출 하나의 GMS 사용량 추정. prices를 주면(결과 파일에 저장된 요금표) 그걸 쓴다"""
    if not tokens:
        return 0.0
    input_price, output_price = (prices or PRICES)[model]
    output_tokens = tokens["output"] + tokens["thinking"]
    usd = (tokens["input"] * input_price + output_tokens * output_price) / 1_000_000
    return usd * GMS_UNITS_PER_USD


def parse_steps(text: str | None) -> set[int] | None:
    """'1-5' 또는 '1,3,8' → 단계 순서 집합"""
    if not text:
        return None
    orders = set()
    for part in text.split(","):
        start, _, end = part.partition("-")
        orders.update(range(int(start), int(end or start) + 1))
    return orders


def next_run_path(video_id: str) -> Path:
    numbers = [int(p.stem.rsplit("_", 1)[1]) for p in RUNS_DIR.glob(f"{video_id}_*.json")]
    return RUNS_DIR / f"{video_id}_{max(numbers, default=0) + 1}.json"


def run(sample_path: Path, providers: list[str], orders: set[int] | None) -> None:
    try:
        key = KeySettings().gms_api_key
    except ValidationError:
        raise SystemExit("ai/.env에 GMS_API_KEY를 넣으세요") from None
    data = json.loads(sample_path.read_text(encoding="utf-8"))
    GuideInput.model_validate(data)

    steps, moved = move_misplaced(sorted(data["steps"], key=lambda s: s["order"]))
    chosen = [s for s in steps if orders is None or s["order"] in orders]
    jobs = [(provider, step) for step in chosen for provider in providers]
    print(f"{len(chosen)}단계 × {len(providers)}모델 = {len(jobs)}번 호출")

    started = time.time()
    calls = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(run_one, provider, step, key) for provider, step in jobs]
        for future in as_completed(futures):
            call = future.result()
            calls.append(call)
            state = (
                f"오류 {call['error'][:60]}" if call["error"] else f"문제 {len(call['problems'])}"
            )
            name = f"{call['provider']} {call['stepId']}"
            print(f"  [{len(calls)}/{len(jobs)}] {name} {call['seconds']}초 {state}")

    result = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "sample": sample_path.relative_to(AI_ROOT).as_posix(),
        "videoId": data["videoId"],
        "promptVersion": PROMPT_VERSION,
        "prompt": PROMPT,
        "schema": SCHEMA,
        "models": {p: MODELS[p] for p in providers},
        "prices": {MODELS[p]: PRICES[MODELS[p]] for p in providers},
        "elapsedSeconds": round(time.time() - started, 1),
        "moved": moved,
        "steps": [
            {
                "stepId": s["stepId"],
                "order": s["order"],
                "partLabel": s["partLabel"],
                "makeup": s["makeup"],
                "product": s.get("product"),
                "inputs": inputs_of(s),
                "message": user_message(s, inputs_of(s)),
            }
            for s in chosen
        ],
        "calls": calls,
    }
    path = next_run_path(data["videoId"])
    RUNS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {path.relative_to(AI_ROOT).as_posix()} ({result['elapsedSeconds']:.0f}초)")
    print("GMS 사용량 추정 (사이트 숫자와 같은 단위)")
    for provider in providers:
        usage = sum(
            gms_usage(c["model"], c.get("tokens")) for c in calls if c["provider"] == provider
        )
        print(f"  {provider} {MODELS[provider]}: {usage:.0f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE, help="가이드 입력 JSON")
    parser.add_argument("--models", default=",".join(MODELS), help="gpt,gemini,claude 중 고르기")
    parser.add_argument("--steps", help="단계 순서. 예) 1-5 또는 1,3,8 (없으면 모두)")
    args = parser.parse_args()

    providers = [p.strip() for p in args.models.split(",")]
    unknown = [p for p in providers if p not in MODELS]
    if unknown:
        raise SystemExit(f"모르는 모델 {unknown}. {list(MODELS)} 중에서 고르세요")
    run(args.sample.resolve(), providers, parse_steps(args.steps))


if __name__ == "__main__":
    main()
