"""설명 생성에 대표 장면 이미지를 넣을 때와 뺄 때 비교 (개발용, S15P31A306-277).

운영 코드(step_inputs·user_message·check_explanation)로 샘플 단계마다 설명을 만들고 확인한다.
이미지 없음은 운영 지시문 그대로 부른다. 이미지 있음은 11.02에 운영에서 뺀 이미지 줄 세 개를
지시문에 다시 넣고, 샘플 JSON의 images(운영 입력에서는 버리는 칸)를 frames 폴더에서 읽어 보낸다.
한 회차 안에서 두 조건을 함께 돌려 응답 시간이 같은 조건에서 재지게 한다.

실행 (ai/ 폴더에서, .env에 GMS_API_KEY 필요):
  uv run python tools/explain_image_compare.py                      두 조건 각 1번
  uv run python tools/explain_image_compare.py --runs 3 --steps 1-5
결과 → tools/explain_image_runs/<영상 ID>_<회차>.json
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.clients.llm import ClaudeLlm, Llm, LlmError, LlmImage, LlmUsage
from app.core.config import get_settings
from app.schemas.guide import GuideInput, GuideInputStep
from app.schemas.guide_job import StepExplanation
from app.services.explanation_checker import (
    NOTICE_KINDS,
    check_explanation,
    explanation_sentences,
)
from app.services.guide_input import move_misplaced_facts
from app.services.step_explainer import PROMPT, step_inputs, user_message

TOOLS_DIR = Path(__file__).resolve().parent
RUNS_DIR = TOOLS_DIR / "explain_image_runs"
DEFAULT_SAMPLE = AI_ROOT / "samples" / "local_01" / "guide_input.json"

# (찾을 글, 바꿀 글). 운영 지시문을 11.02 전 이미지 지시문(step_explanation@0683b974)으로 되돌린다
IMAGE_LINE = "사용자 메시지 앞에 붙은 이미지는 이 단계의 대표 장면이다.\n"
IMAGE_RULE = (
    "- 이미지는 입력의 말이 가리키는 곳과 모양을 알아보는 데만 쓴다. "
    "이미지에서 본 것을 새 동작이나 방식으로 더하지 않는다.\n"
)
IMAGE_EDITS = [
    ("이 내용에 있는 것만 쓴다.\n", "이 내용에 있는 것만 쓴다.\n" + IMAGE_LINE),
    ("이 단계 입력으로 뜻을", "이 단계 입력과 이미지로 뜻을"),
    ("- 입력을 뒤집어 반대 경우를", IMAGE_RULE + "- 입력을 뒤집어 반대 경우를"),
]
MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# 공개 요금 (달러, 100만 토큰당 입력·출력). 생각 토큰은 출력 요금. GMS 사이트 숫자 = 달러 × 10,000
PRICES = {"claude-haiku-5-5": (0.10, 0.50)}
GMS_UNITS_PER_USD = 10_000

CONDITIONS = ("images", "no_images")
LABELS = {"images": "이미지 있음", "no_images": "이미지 없음"}


@dataclass(frozen=True)
class SampleImage:
    name: str
    mime_type: str
    data: bytes


def image_prompt(prompt: str) -> str:
    """운영 지시문이 바뀌어 넣을 자리를 못 찾으면 멈춘다. 다른 지시문끼리 비교하지 않게."""
    if "이미지" in prompt:
        raise SystemExit("운영 지시문에 이미지 줄이 있음. IMAGE_EDITS를 고치세요")
    for old, new in IMAGE_EDITS:
        if prompt.count(old) != 1:
            raise SystemExit(f"운영 지시문에서 이미지 줄 넣을 자리를 찾지 못함: {old.strip()}")
        prompt = prompt.replace(old, new)
    return prompt


def prompt_version(prompt: str) -> str:
    return f"step_explanation@{hashlib.sha256(prompt.encode()).hexdigest()[:8]}"


def load_images(sample: dict, frames_dir: Path, step_ids: set[str]) -> dict[str, list[SampleImage]]:
    """샘플 이미지 주소(예시 주소)의 파일 이름으로 frames 폴더의 파일을 읽는다.

    frames 폴더는 영상 장면이라 git에 넣지 않는다(.gitignore).
    """
    if not frames_dir.is_dir():
        raise SystemExit(f"{frames_dir}가 없음. 장면 이미지는 git에 없으니 받아서 넣으세요")
    images = {}
    for step in sample["steps"]:
        if step["stepId"] not in step_ids:
            continue
        names = [image["url"].rsplit("/", 1)[-1] for image in step.get("images", [])]
        if not names:
            raise SystemExit(f"{step['stepId']}에 images가 없음. 이미지 있는 샘플을 쓰세요")
        loaded = []
        for name in names:
            mime_type = MIME_TYPES[Path(name).suffix.lower()]
            loaded.append(SampleImage(name, mime_type, (frames_dir / name).read_bytes()))
        images[step["stepId"]] = loaded
    return images


def gms_usage(model: str, usage: dict) -> float:
    input_price, output_price = PRICES[model]
    output_tokens = usage["output"] + usage["thinking"]
    usd = (usage["input"] * input_price + output_tokens * output_price) / 1_000_000
    return usd * GMS_UNITS_PER_USD


def usage_dict(usage: LlmUsage) -> dict:
    data = asdict(usage)
    return {
        "input": data["input_tokens"],
        "output": data["output_tokens"],
        "thinking": data["thinking_tokens"],
    }


async def run_step(llm: Llm, step: GuideInputStep, images: list[LlmImage], prompt: str) -> dict:
    record: dict = {"stepId": step.step_id, "order": step.order, "partLabel": step.part_label}
    started = time.perf_counter()
    try:
        result = await llm.generate(
            system=prompt,
            text=user_message(step, step_inputs(step)),
            images=images,
            output=StepExplanation,
        )
    except LlmError as e:
        record.update(error=f"설명 실패: {e} ({e.kind})")
        return record
    record.update(
        model=result.model,
        explanation=result.output.model_dump(mode="json", by_alias=True),
        sentences=[
            {"id": s.id, "text": s.text, "sources": s.sources}
            for s in explanation_sentences(result.output)
        ],
        usage={"explain": usage_dict(result.usage)},
        seconds={"explain": round(time.perf_counter() - started, 1)},
    )
    started = time.perf_counter()
    try:
        check = await check_explanation(llm, step, result.output)
    except LlmError as e:
        record.update(error=f"확인 실패: {e} ({e.kind})")
        return record
    record["seconds"]["check"] = round(time.perf_counter() - started, 1)
    record["usage"]["check"] = usage_dict(check.usage)
    record.update(
        passed=check.passed,
        problems=[
            {"id": p.sentence_id, "text": p.text, "kind": p.kind, "reason": p.reason}
            for p in check.problems
        ],
        error=None,
    )
    return record


async def run_once(
    llm: Llm,
    steps: list[GuideInputStep],
    images: dict[str, list[LlmImage]],
    prompts: dict[str, str],
) -> dict[str, list[dict]]:
    """두 조건을 단계마다 번갈아 넣어, 동시 호출 자리를 기다리는 시간이 한쪽에 몰리지 않게 한다."""
    jobs = []
    for step in steps:
        for condition in CONDITIONS:
            step_images = images[step.step_id] if condition == "images" else []
            jobs.append((condition, run_step(llm, step, step_images, prompts[condition])))
    results = await asyncio.gather(*(job for _, job in jobs))
    by_condition: dict[str, list[dict]] = {c: [] for c in CONDITIONS}
    for (condition, _), record in zip(jobs, results, strict=True):
        by_condition[condition].append(record)
    return by_condition


def summarize(runs: list[dict[str, list[dict]]], model: str) -> dict[str, dict]:
    summary = {}
    for condition in CONDITIONS:
        records = [r for run in runs for r in run[condition]]
        done = [r for r in records if not r.get("error")]
        kinds = Counter(p["kind"] for r in done for p in r["problems"])
        explain_usage = [r["usage"]["explain"] for r in done]
        all_usage = [u for r in done for u in r["usage"].values()]
        n = len(done) or 1
        summary[condition] = {
            "steps": len(records),
            "errors": len(records) - len(done),
            "passed": sum(r["passed"] for r in done),
            "failures": {k: v for k, v in kinds.most_common() if k not in NOTICE_KINDS},
            "notices": {k: v for k, v in kinds.most_common() if k in NOTICE_KINDS},
            "sentencesPerStep": round(sum(len(r["sentences"]) for r in done) / n, 2),
            "explainTokensPerStep": {
                key: round(sum(u[key] for u in explain_usage) / n)
                for key in ("input", "output", "thinking")
            },
            "explainGmsPerRun": round(
                sum(gms_usage(model, u) for u in explain_usage) / len(runs), 1
            ),
            "totalGmsPerRun": round(sum(gms_usage(model, u) for u in all_usage) / len(runs), 1),
            "explainSecondsPerStep": round(sum(r["seconds"]["explain"] for r in done) / n, 1),
        }
    return summary


def print_summary(summary: dict[str, dict], runs: int) -> None:
    print(f"\n요약 ({runs}회차 합계, 단계 기준)")
    for condition, s in summary.items():
        checked = s["steps"] - s["errors"]
        rate = s["passed"] / max(checked, 1) * 100
        t = s["explainTokensPerStep"]
        print(f"[{LABELS[condition]}]")
        print(f"  확인 통과 {s['passed']}/{checked} ({rate:.0f}%), 오류 {s['errors']}")
        print(f"  걸린 종류 {s['failures'] or '없음'}")
        print(f"  알림 {s['notices'] or '없음'}")
        print(f"  단계당 문장 {s['sentencesPerStep']}개, 설명 {s['explainSecondsPerStep']}초")
        print(f"  단계당 설명 토큰 입력 {t['input']}·답 {t['output']}·생각 {t['thinking']}")
        print(f"  회차당 GMS 설명 {s['explainGmsPerRun']}, 확인 포함 {s['totalGmsPerRun']}")


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


async def run(sample_path: Path, frames_dir: Path, runs: int, orders: set[int] | None) -> None:
    settings = get_settings()
    if settings.gms_api_key is None:
        raise SystemExit("ai/.env에 GMS_API_KEY를 넣으세요")
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    guide_input = GuideInput.model_validate(sample)
    steps = [
        s for s in move_misplaced_facts(guide_input).steps if orders is None or s.order in orders
    ]
    images = load_images(sample, frames_dir, {s.step_id for s in steps})
    prompts = {"images": image_prompt(PROMPT), "no_images": PROMPT}
    llm = ClaudeLlm(settings)
    calls = len(steps) * len(CONDITIONS) * runs
    print(f"{len(steps)}단계 × 2조건 × {runs}회차 = 설명 {calls}번 (+ 확인 같은 수)")

    started = time.time()
    results = []
    for i in range(runs):
        results.append(await run_once(llm, steps, images, prompts))
        done = {c: sum(1 for r in results[-1][c] if not r.get("error")) for c in CONDITIONS}
        print(f"  {i + 1}회차 끝 ({time.time() - started:.0f}초) 성공 {done}")

    summary = summarize(results, settings.llm_model)
    output = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "sample": sample_path.relative_to(AI_ROOT).as_posix(),
        "videoId": guide_input.video_id,
        "model": settings.llm_model,
        "effort": settings.llm_effort,
        "promptVersions": {c: prompt_version(p) for c, p in prompts.items()},
        "prompts": prompts,
        "steps": [
            {
                "stepId": s.step_id,
                "order": s.order,
                "partLabel": s.part_label,
                "inputs": step_inputs(s),
                "images": [image.name for image in images[s.step_id]],
            }
            for s in steps
        ],
        "summary": summary,
        "runs": results,
    }
    path = next_run_path(guide_input.video_id)
    RUNS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(summary, runs)
    print(f"\n저장: {path.relative_to(AI_ROOT).as_posix()} ({time.time() - started:.0f}초)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE, help="가이드 입력 JSON")
    parser.add_argument("--frames", type=Path, help="이미지 폴더 (없으면 샘플 옆 frames)")
    parser.add_argument("--runs", type=int, default=1, help="회차 수")
    parser.add_argument("--steps", help="단계 순서. 예) 1-5 또는 1,3,8 (없으면 모두)")
    args = parser.parse_args()
    sample = args.sample.resolve()
    frames = (args.frames or sample.parent / "frames").resolve()
    asyncio.run(run(sample, frames, args.runs, parse_steps(args.steps)))


if __name__ == "__main__":
    main()
