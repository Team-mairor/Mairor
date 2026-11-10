"""운영 가이드 작업 하나의 Phoenix 기록을 내려받아 구간별 시간과 결과를 파일로 둔다(개발용).

AI 작업 ID(콜백의 jobId, BE analysis_jobs.ai_job_id)로 guide_job 기록을 찾고, 같은 trace에서
영역 구간(guide_area · download_frames · face_landmarks · check_frames · build_guide_area)과
callback을 받는다. 설명 만들기(explain_step · check_step · messages.create)는 받지 않는다.
<저장 폴더>/<AI 작업 ID>/에 두 파일을 둔다.
- spans.json: 구간마다 시작 · 끝 시각, 걸린 밀리초, 상태, 입력 · 출력.
  guide_job 출력은 빼고 아래 파일에 둔다.
- callback_body.json: guide_job 출력, 곧 BE에 보낸 콜백 본문(가이드와 영역).
영역 구간은 영역 작업 자리를 얻은 뒤 시작하므로,
guide_area 시작 - guide_job 시작을 기다린 시간으로 낸다.

Phoenix 로그인이 켜져 있어 API 키가 필요하다. 키는 환경 변수 PHOENIX_API_KEY에서만 읽고
화면 · 파일에 남기지 않는다. 주소는 PHOENIX_URL로 바꿀 수 있다(기본은 팀 인프라 서버).
실행 (ai/ 폴더에서): uv run --no-sync python tools/fetch_phoenix_trace.py <AI 작업 ID> <저장 폴더>
"""

import json
import os
import sys
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx2

DEFAULT_URL = "https://k15a306.p.ssafy.io/phoenix"
PROJECT = "ai-guide"
JOB_SPAN = "guide_job"
AREA_SPAN = "guide_area"
SPAN_NAMES = (
    JOB_SPAN,
    AREA_SPAN,
    "download_frames",
    "face_landmarks",
    "check_frames",
    "build_guide_area",
    "callback",
)
PAGE_LIMIT = 1000
TIMEOUT_SECONDS = 60
KST = timezone(timedelta(hours=9))
SPANS_FILE = "spans.json"
CALLBACK_FILE = "callback_body.json"


class FetchError(Exception):
    """기록을 받지 못한 이유. 화면에 그대로 찍는다."""


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "사용법: uv run --no-sync python tools/fetch_phoenix_trace.py <AI 작업 ID> <저장 폴더>"
        )
        sys.exit(1)
    key = os.environ.get("PHOENIX_API_KEY", "").strip()
    if not key:
        print(
            "PHOENIX_API_KEY 환경 변수가 비어 있습니다. 같은 터미널에서 키를 넣고 다시 실행하세요."
        )
        sys.exit(1)

    job_id = sys.argv[1].strip()
    base_url = os.environ.get("PHOENIX_URL", DEFAULT_URL).rstrip("/")
    try:
        with httpx2.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=TIMEOUT_SECONDS,
        ) as client:
            job_span = find_job_span(fetch_spans(client, [("name", JOB_SPAN)]), job_id)
            trace_id = job_span["context"]["trace_id"]
            params = [("trace_id", trace_id)] + [("name", name) for name in SPAN_NAMES]
            spans = list(fetch_spans(client, params))
    except FetchError as error:
        print(error)
        sys.exit(1)

    rows = summarize(spans)
    folder = save(job_id, trace_id, rows, Path(sys.argv[2]))
    print(f"AI 작업 ID {job_id} · trace {trace_id}")
    for line in report_lines(rows):
        print(line)
    print(f"저장: {folder}")


def fetch_spans(
    client: httpx2.Client, params: Sequence[tuple[str, str]]
) -> Iterator[dict[str, Any]]:
    """조건에 맞는 span을 모두 받는다. 한 번에 PAGE_LIMIT개씩, next_cursor가 없을 때까지."""
    cursor: str | None = None
    while True:
        query = [*params, ("limit", str(PAGE_LIMIT))]
        if cursor:
            query.append(("cursor", cursor))
        try:
            response = client.get(f"/v1/projects/{PROJECT}/spans", params=query)
        except httpx2.TransportError as error:
            raise FetchError(f"Phoenix에 연결하지 못했습니다: {type(error).__name__}") from error
        if response.status_code in (401, 403):
            raise FetchError(
                f"Phoenix가 키를 받지 않았습니다(HTTP {response.status_code}). "
                "키가 맞는지, 만료되지 않았는지 확인하세요."
            )
        if not response.is_success:
            raise FetchError(f"Phoenix 응답 HTTP {response.status_code}: {response.text[:200]}")
        body = response.json()
        yield from body["data"]
        cursor = body.get("next_cursor")
        if not cursor:
            return


def find_job_span(spans: Iterator[dict[str, Any]], job_id: str) -> dict[str, Any]:
    """guide_job 기록 가운데 AI 작업 ID가 같은 것 하나를 고른다. 없거나 둘 이상이면 이유를 올린다.

    작업 ID는 metadata의 job_id를 먼저 보고, 없으면 입력의 jobId를 본다.
    """
    matches = [span for span in spans if span_job_id(span) == job_id]
    if not matches:
        raise FetchError(
            f"AI 작업 ID {job_id}인 guide_job 기록이 없습니다. "
            "ID가 맞는지, 보관 기간(30일)이 지나지 않았는지 확인하세요."
        )
    if len(matches) > 1:
        traces = ", ".join(span["context"]["trace_id"] for span in matches)
        raise FetchError(f"AI 작업 ID {job_id}인 guide_job 기록이 {len(matches)}개입니다: {traces}")
    return matches[0]


def span_job_id(span: Mapping[str, Any]) -> str | None:
    attributes = span.get("attributes") or {}
    metadata = parse_json(attribute(attributes, "metadata"))
    if isinstance(metadata, dict) and metadata.get("job_id"):
        return str(metadata["job_id"])
    inputs = parse_json(attribute(attributes, "input.value"))
    if isinstance(inputs, dict) and inputs.get("jobId"):
        return str(inputs["jobId"])
    return None


def attribute(attributes: Mapping[str, Any], path: str) -> Any:
    """점으로 이은 이름의 속성 값.

    펼친 꼴({"input.value": …})과 겹친 꼴({"input": {"value": …}})을 다 읽는다.
    """
    if path in attributes:
        return attributes[path]
    value: Any = attributes
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def parse_json(value: Any) -> Any:
    """기록에 JSON 글로 들어간 값을 풀어 준다. 글이 아니거나 JSON이 아니면 그대로 둔다."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def summarize(spans: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """span을 시작 시각 순으로 한 줄씩 바꾼다. 시각은 원래 값(UTC)을 그대로 둔다."""
    rows = []
    for span in spans:
        attributes = span.get("attributes") or {}
        start = parse_time(span["start_time"])
        end = parse_time(span["end_time"])
        rows.append(
            {
                "name": span["name"],
                "spanId": span["context"]["span_id"],
                "parentId": span.get("parent_id"),
                "startTime": span["start_time"],
                "endTime": span["end_time"],
                "durationMs": round((end - start) / timedelta(milliseconds=1), 3),
                "statusCode": span["status_code"],
                "statusMessage": span.get("status_message", ""),
                "input": parse_json(attribute(attributes, "input.value")),
                "output": parse_json(attribute(attributes, "output.value")),
            }
        )
    return sorted(rows, key=lambda row: parse_time(row["startTime"]))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def area_wait_ms(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """영역 작업 자리를 기다린 밀리초(guide_area 시작 - guide_job 시작). 하나라도 없으면 None."""
    starts = {row["name"]: parse_time(row["startTime"]) for row in rows}
    if JOB_SPAN not in starts or AREA_SPAN not in starts:
        return None
    return round((starts[AREA_SPAN] - starts[JOB_SPAN]) / timedelta(milliseconds=1), 3)


def save(job_id: str, trace_id: str, rows: Sequence[Mapping[str, Any]], root: Path) -> Path:
    """<root>/<job_id>/에 spans.json과 callback_body.json을 두고 폴더를 돌려준다."""
    folder = root / job_id
    folder.mkdir(parents=True, exist_ok=True)
    callback = next((row["output"] for row in rows if row["name"] == JOB_SPAN), None)
    spans = [{**row, "output": None} if row["name"] == JOB_SPAN else dict(row) for row in rows]
    summary = {
        "jobId": job_id,
        "traceId": trace_id,
        "areaWaitMs": area_wait_ms(rows),
        "spans": spans,
    }
    write_json(folder / SPANS_FILE, summary)
    write_json(folder / CALLBACK_FILE, callback)
    return folder


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def report_lines(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """화면에 찍을 구간별 줄. 시작 시각은 한국 시간으로 바꿔 보여 준다."""
    lines = []
    for row in rows:
        start = parse_time(row["startTime"]).astimezone(KST).strftime("%m-%d %H:%M:%S")
        seconds = row["durationMs"] / 1000
        lines.append(f"{row['name']:<18} 시작 {start}  {seconds:9.1f}초  {row['statusCode']}")
    missing = [name for name in SPAN_NAMES if name not in {row["name"] for row in rows}]
    if missing:
        lines.append(f"없는 구간: {', '.join(missing)}")
    wait = area_wait_ms(rows)
    if wait is not None:
        lines.append(f"영역 자리 기다림: {wait / 1000:.1f}초")
    return lines


if __name__ == "__main__":
    main()
