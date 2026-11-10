"""운영 가이드 작업 결과(콜백 본문)가 약속대로 왔는지 검사하고, 부위 × 단계 상태를 센다(개발용).

tools/fetch_phoenix_trace.py가 받은 기록 폴더(callback_body.json · spans.json)를 읽는다.
검사는 세 가지다.
- 양식: BE와 같은 공유 스키마(shared/guide-job/guide_job_callback.v1.schema.json)로
  칸이 다 있는지, 값 종류가 맞는지 본다.
- 규칙: 서비스 모델(GuideJobResult)에 넣어, 스키마로는 못 보는 칸끼리의 규칙
  (shared/guide-area/README.md 「스키마에 없는 검사」)을 본다.
- 단계 맞춤: 설명(guide.steps)과 영역(area.steps)의 단계 ID가 같은 순서로 빠짐없이 있는지 본다.
표는 세 가지다.
- 부위별: 화장 종류마다 하위 단계 상태 수. 기본 영역(template)은 이유가 notAnalyzed인 것
  (분석하지 않는 부위)과 그 밖의 것(분석했지만 못 찾음)을 나눈다.
- 단계별: 하위 단계마다 부위 · 상태 · 이유 · 기본 가이드 키 · 찾은 자리.
- 사진: spans.json의 받은 사진 · 받기 실패 · 얼굴 점 · 사진 판정 수.
  작업 전체 수이고, 단계별 사진 수는 기록에 없다.
결과는 화면에 찍고 <기록 폴더>/ops_check.json에 둔다.
실행 (ai/ 폴더에서): uv run --no-sync python tools/ops_guide_job_check.py <기록 폴더>
"""

import json
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, get_args

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaError
from pydantic import ValidationError

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_job import GuideJobResult
from app.schemas.manifest import Makeup
from tools.export_guide_schema import GUIDE_JOB_CALLBACK_PATH
from tools.fetch_phoenix_trace import CALLBACK_FILE, SPANS_FILE

OUTPUT_FILE = "ops_check.json"
NOT_ANALYZED = "notAnalyzed"
MESSAGE_LIMIT = 200
PARTS: tuple[str, ...] = get_args(Makeup)
PART_NAMES = {
    "foundation": "베이스",
    "eyeshadow": "섀도",
    "eyeliner": "아이라인",
    "blush": "블러셔",
    "lip": "립",
    "brow": "눈썹",
    "mascara": "마스카라",
    "contour": "쉐딩",
    "highlight": "하이라이트",
    "other": "기타",
}
STATUS_NAMES = {
    "extracted": "찾음",
    "template": "기본 영역",
    "notApplicable": "해당 없음",
    "failed": "실패",
}


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run --no-sync python tools/ops_guide_job_check.py <기록 폴더>")
        sys.exit(1)
    folder = Path(sys.argv[1])
    body = read_json(folder / CALLBACK_FILE)
    spans = read_json(folder / SPANS_FILE)
    report = check(body, spans)
    path = save(report, folder)
    for line in report_lines(report):
        print(line)
    print(f"저장: {path}")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check(body: Mapping[str, Any], spans: Mapping[str, Any]) -> dict[str, Any]:
    """콜백 본문과 구간 기록으로 검사 세 가지와 표 세 가지를 만든다."""
    return {
        "jobId": body.get("jobId"),
        "stepCount": len(area_steps(body)),
        "schemaErrors": schema_errors(body),
        "ruleErrors": rule_errors(body),
        "stepMatchErrors": step_match_errors(body),
        "parts": part_table(body),
        "steps": step_rows(body),
        "photos": photo_counts(spans),
    }


def area_steps(body: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list((body.get("area") or {}).get("steps") or [])


def guide_steps(body: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list((body.get("guide") or {}).get("steps") or [])


def schema_errors(body: Mapping[str, Any]) -> list[str]:
    """BE와 같은 공유 스키마로 검사해, 걸린 곳을 모두 「어느 칸: 무엇이 틀림」으로 낸다."""
    schema = json.loads(GUIDE_JOB_CALLBACK_PATH.read_text(encoding="utf-8"))
    errors = Draft202012Validator(schema).iter_errors(body)
    leaves = [leaf for error in errors for leaf in leaf_errors(error)]
    lines = [f"{path_text(body, leaf.absolute_path)}: {leaf.message}" for leaf in leaves]
    return sorted(set(short(line) for line in lines))


def leaf_errors(error: JsonSchemaError) -> Iterator[JsonSchemaError]:
    """「둘 중 하나여야 함」(anyOf) 오류를 실제로 틀린 칸까지 내려가 꺼낸다.

    area · guide는 「값 또는 null」이라, 안쪽 칸 하나가 틀려도 스키마는 area 전체가 틀렸다고만 한다.
    null 쪽 갈래(값이 null이어야 함)는 원인이 아니라서 뺀다.
    """
    if not error.context:
        yield error
        return
    for sub_error in error.context:
        if sub_error.validator == "type" and sub_error.validator_value == "null":
            continue
        yield from leaf_errors(sub_error)


def rule_errors(body: Mapping[str, Any]) -> list[str]:
    """서비스 모델에 넣어 본다. 칸끼리의 규칙을 어기면 걸린 곳마다 한 줄씩 낸다."""
    try:
        GuideJobResult.model_validate(body)
    except ValidationError as error:
        return [
            short(f"{path_text(body, detail['loc'])}: {detail['msg']}") for detail in error.errors()
        ]
    return []


def step_match_errors(body: Mapping[str, Any]) -> list[str]:
    """설명과 영역의 단계 ID가 같은 순서로 빠짐없이 있는지 본다.

    설명이나 영역이 통째로 없으면 맞춰 볼 수 없다고 낸다.
    """
    if body.get("guide") is None or body.get("area") is None:
        return ["설명(guide)이나 영역(area)이 없어 단계를 맞춰 볼 수 없습니다"]
    guide_ids = [step.get("stepId") for step in guide_steps(body)]
    area_ids = [step.get("stepId") for step in area_steps(body)]
    errors = []
    for name, ids in (("설명", guide_ids), ("영역", area_ids)):
        repeated = sorted(str(key) for key, count in Counter(ids).items() if count > 1)
        if repeated:
            errors.append(f"{name}에 겹치는 단계: {', '.join(repeated)}")
    only_guide = [str(step) for step in guide_ids if step not in set(area_ids)]
    only_area = [str(step) for step in area_ids if step not in set(guide_ids)]
    if only_guide:
        errors.append(f"설명에만 있는 단계: {', '.join(only_guide)}")
    if only_area:
        errors.append(f"영역에만 있는 단계: {', '.join(only_area)}")
    if not errors and guide_ids != area_ids:
        errors.append("설명과 영역의 단계 순서가 다릅니다")
    return errors


def part_table(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    """화장 종류마다 단계 수와 하위 단계 상태 수. 결과에 없는 종류도 0으로 넣는다."""
    rows: dict[str, dict[str, Any]] = {part: empty_part(part) for part in PARTS}
    for step in area_steps(body):
        makeup = str(step.get("makeup"))
        row = rows.setdefault(makeup, empty_part(makeup))
        row["steps"] += 1
        for sub_step in step.get("subSteps") or []:
            status = sub_step.get("status")
            reasons = list(sub_step.get("reasons") or [])
            row["subSteps"] += 1
            if status == "template" and NOT_ANALYZED in reasons:
                row["templateNotAnalyzed"] += 1
                continue
            key = "templateNotFound" if status == "template" else str(status)
            row[key] = row.get(key, 0) + 1
            if status in ("template", "failed"):
                row["reasons"].update(reasons)
    return [{**row, "reasons": dict(sorted(row["reasons"].items()))} for row in rows.values()]


def empty_part(makeup: str) -> dict[str, Any]:
    return {
        "makeup": makeup,
        "steps": 0,
        "subSteps": 0,
        "extracted": 0,
        "templateNotAnalyzed": 0,
        "templateNotFound": 0,
        "notApplicable": 0,
        "failed": 0,
        "reasons": Counter(),
    }


def step_rows(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    """하위 단계마다 한 줄. 찾은 자리는 guideSets의 region 이름이다."""
    rows = []
    for step in area_steps(body):
        for sub_step in step.get("subSteps") or []:
            regions = {guide_set.get("region") for guide_set in sub_step.get("guideSets") or []}
            rows.append(
                {
                    "stepId": step.get("stepId"),
                    "subStepId": sub_step.get("subStepId"),
                    "makeup": step.get("makeup"),
                    "status": sub_step.get("status"),
                    "reasons": list(sub_step.get("reasons") or []),
                    "templateId": sub_step.get("templateId"),
                    "regions": sorted(str(region) for region in regions),
                }
            )
    return rows


def photo_counts(spans: Mapping[str, Any]) -> dict[str, Any]:
    """구간 기록에서 사진 수를 꺼낸다. 구간이 없으면 그 칸은 None이다."""
    by_name = {span["name"]: span for span in spans.get("spans") or []}
    download = by_name.get("download_frames") or {}
    landmarks = by_name.get("face_landmarks") or {}
    checked = by_name.get("check_frames") or {}
    return {
        "frames": (download.get("input") or {}).get("frames"),
        "missing": (download.get("output") or {}).get("missing"),
        "landmarks": landmarks.get("output"),
        "checked": checked.get("output"),
    }


def path_text(body: Mapping[str, Any], path: Iterable[Any]) -> str:
    """오류 위치를 area.steps[13](s14).subSteps[0].status처럼 읽기 쉽게 바꾼다."""
    parts = list(path)
    if not parts:
        return "(본문 전체)"
    text = ""
    for index, part in enumerate(parts):
        if isinstance(part, int):
            text += f"[{part}]"
            step_id = step_id_at(body, parts[:index], part)
            if step_id:
                text += f"({step_id})"
        else:
            text += f".{part}" if text else str(part)
    return text


def step_id_at(body: Mapping[str, Any], parent: Sequence[Any], index: int) -> str | None:
    """area.steps · guide.steps의 몇 번째인지가 나오면 그 단계 ID를 돌려준다."""
    if len(parent) != 2 or parent[0] not in ("area", "guide") or parent[1] != "steps":
        return None
    steps = area_steps(body) if parent[0] == "area" else guide_steps(body)
    if index >= len(steps):
        return None
    step = steps[index]
    return str(step.get("stepId")) if isinstance(step, Mapping) else None


def short(text: str) -> str:
    return text if len(text) <= MESSAGE_LIMIT else text[: MESSAGE_LIMIT - 1] + "…"


def save(report: Mapping[str, Any], folder: Path) -> Path:
    path = folder / OUTPUT_FILE
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def report_lines(report: Mapping[str, Any]) -> list[str]:
    """화면에 찍을 줄. 표는 문서에 그대로 옮길 수 있게 마크다운으로 낸다."""
    lines = [f"검사 대상: {report['jobId']} (단계 {report['stepCount']}개)"]
    for label, key in (
        ("양식 검사", "schemaErrors"),
        ("규칙 검사", "ruleErrors"),
        ("단계 맞춤", "stepMatchErrors"),
    ):
        errors = report[key]
        lines.append(f"{label}: 통과" if not errors else f"{label}: {len(errors)}곳 걸림")
        lines.extend(f"  - {error}" for error in errors)
    lines += ["", "[부위별]", *part_lines(report["parts"])]
    lines += ["", "[단계별]", *step_lines(report["steps"])]
    lines += ["", "[사진]", *photo_lines(report["photos"])]
    return lines


def part_lines(parts: Sequence[Mapping[str, Any]]) -> list[str]:
    columns = ("steps", "extracted", "templateNotAnalyzed", "templateNotFound")
    columns += ("notApplicable", "failed")
    rows = []
    for part in parts:
        reasons = ", ".join(f"{key} {count}" for key, count in part["reasons"].items())
        cells = [PART_NAMES.get(part["makeup"], part["makeup"])]
        rows.append(cells + [str(part[column]) for column in columns] + [reasons or "-"])
    total = ["합계"] + [str(sum(part[column] for part in parts)) for column in columns] + [""]
    headers = ["부위", "단계", "찾음", "기본(분석 안 함)", "기본(못 찾음)", "해당 없음", "실패"]
    return markdown_table([*headers, "못 찾음·실패 이유"], [*rows, total])


def step_lines(steps: Sequence[Mapping[str, Any]]) -> list[str]:
    rows = [
        [
            str(step["subStepId"]),
            PART_NAMES.get(str(step["makeup"]), str(step["makeup"])),
            STATUS_NAMES.get(str(step["status"]), str(step["status"])),
            ", ".join(step["reasons"]) or "-",
            str(step["templateId"] or "-"),
            ", ".join(step["regions"]) or "-",
        ]
        for step in steps
    ]
    headers = ["하위 단계", "부위", "상태", "이유", "기본 가이드 키", "찾은 자리"]
    return markdown_table(headers, rows)


def photo_lines(photos: Mapping[str, Any]) -> list[str]:
    def counts(value: Any) -> str:
        if not isinstance(value, Mapping):
            return "-"
        return ", ".join(f"{key} {count}" for key, count in value.items())

    return [
        f"받은 사진: {photos['frames']}",
        f"받기 실패: {photos['missing']}",
        f"얼굴 점: {counts(photos['landmarks'])}",
        f"사진 판정: {counts(photos['checked'])}",
    ]


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


if __name__ == "__main__":
    main()
