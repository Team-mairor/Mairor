import json

import pytest

from tools.fetch_phoenix_trace import (
    CALLBACK_FILE,
    SPANS_FILE,
    FetchError,
    area_wait_ms,
    attribute,
    find_job_span,
    report_lines,
    save,
    summarize,
)

TRACE = "50a78beecada66c76f8087573b54ffc7"


def make_span(name, start, end, *, span_id, inputs=None, output=None, metadata=None, nested=False):
    attributes = {"input.value": json.dumps(inputs or {}), "metadata": json.dumps(metadata or {})}
    if output is not None:
        attributes["output.value"] = json.dumps(output)
    if nested:
        attributes = {
            "input": {"value": attributes["input.value"]},
            "metadata": attributes["metadata"],
            **({"output": {"value": attributes["output.value"]}} if output is not None else {}),
        }
    return {
        "name": name,
        "context": {"trace_id": TRACE, "span_id": span_id},
        "span_kind": "CHAIN",
        "parent_id": None,
        "start_time": start,
        "end_time": end,
        "status_code": "UNSET",
        "status_message": "",
        "attributes": attributes,
    }


def test_attribute_reads_flat_and_nested_keys():
    """Phoenix가 속성을 펼친 꼴로 줄지 겹친 꼴로 줄지 문서에 정해져 있지 않아 둘 다 읽어야 한다."""
    assert attribute({"input.value": "a"}, "input.value") == "a"
    assert attribute({"input": {"value": "b"}}, "input.value") == "b"
    assert attribute({"input": {}}, "input.value") is None


def test_find_job_span_matches_metadata_or_input_job_id():
    """운영 기록은 metadata에 job_id가 있지만, 예전 기록처럼 입력의 jobId만 있어도 찾아야 한다."""
    by_metadata = make_span(
        "guide_job",
        "2026-11-06T02:31:57Z",
        "2026-11-06T02:42:30Z",
        span_id="a",
        metadata={"job_id": "job-1"},
    )
    by_input = make_span(
        "guide_job",
        "2026-11-04T05:00:00Z",
        "2026-11-04T05:12:00Z",
        span_id="b",
        inputs={"jobId": "job-2"},
    )
    other = make_span(
        "guide_job",
        "2026-11-05T00:00:00Z",
        "2026-11-05T00:01:00Z",
        span_id="c",
        metadata={"job_id": "job-3"},
    )

    assert find_job_span(iter([other, by_metadata]), "job-1") is by_metadata
    assert find_job_span(iter([by_input, other]), "job-2") is by_input


def test_find_job_span_stops_when_missing_or_duplicated():
    """없는 ID나 같은 ID 두 건은 엉뚱한 기록을 받지 않도록 이유를 내고 멈춰야 한다."""
    first = make_span(
        "guide_job",
        "2026-11-06T02:00:00Z",
        "2026-11-06T02:10:00Z",
        span_id="a",
        metadata={"job_id": "job-1"},
    )
    second = {**first, "context": {"trace_id": "t2", "span_id": "b"}}

    with pytest.raises(FetchError, match="없습니다"):
        find_job_span(iter([first]), "job-9")
    with pytest.raises(FetchError, match="2개"):
        find_job_span(iter([first, second]), "job-1")


def operation_spans(nested=False):
    return [
        make_span(
            "callback",
            "2026-11-06T02:42:29.500Z",
            "2026-11-06T02:42:30Z",
            span_id="f",
            output={"attempts": 1, "delivered": True},
            nested=nested,
        ),
        make_span(
            "guide_job",
            "2026-11-06T02:31:57Z",
            "2026-11-06T02:42:30Z",
            span_id="a",
            inputs={"jobId": "job-1", "frames": 3},
            output={"status": "COMPLETED"},
            nested=nested,
        ),
        make_span(
            "guide_area",
            "2026-11-06T02:31:57.250Z",
            "2026-11-06T02:40:00Z",
            span_id="b",
            inputs={"frames": 3},
            nested=nested,
        ),
        make_span(
            "download_frames",
            "2026-11-06T02:31:57.300Z",
            "2026-11-06T02:32:57.300Z",
            span_id="c",
            inputs={"frames": 3},
            output={"missing": 0},
            nested=nested,
        ),
    ]


def test_summarize_orders_by_start_and_reads_durations():
    """화면은 구간을 시작 순으로 보여 준다.

    받은 순서와 상관없이 시작 순으로 놓고 걸린 시간을 밀리초로 낸다.
    """
    rows = summarize(operation_spans(nested=True))

    assert [row["name"] for row in rows] == [
        "guide_job",
        "guide_area",
        "download_frames",
        "callback",
    ]
    assert rows[0]["durationMs"] == 633_000
    assert rows[2]["durationMs"] == 60_000
    assert rows[2]["output"] == {"missing": 0}
    assert rows[1]["output"] is None
    assert area_wait_ms(rows) == 250


def test_save_keeps_callback_body_apart(tmp_path):
    """콜백 본문은 크고 결과표 재료라 따로 두고, 구간 파일에는 같은 내용을 두 번 넣지 않는다."""
    rows = summarize(operation_spans())

    folder = save("job-1", TRACE, rows, tmp_path)

    summary = json.loads((folder / SPANS_FILE).read_text(encoding="utf-8"))
    callback = json.loads((folder / CALLBACK_FILE).read_text(encoding="utf-8"))
    assert folder == tmp_path / "job-1"
    assert summary["traceId"] == TRACE
    assert summary["areaWaitMs"] == 250
    assert summary["spans"][0]["name"] == "guide_job"
    assert summary["spans"][0]["output"] is None
    assert callback == {"status": "COMPLETED"}


def test_report_lines_show_korean_time_and_missing_spans():
    """사람이 Phoenix 화면(한국 시간)과 바로 맞춰 보게 한다.

    시작 시각을 한국 시간으로 찍고, 빠진 구간을 알린다.
    """
    lines = report_lines(summarize(operation_spans()))

    assert lines[0].startswith("guide_job")
    assert "11-06 11:31:57" in lines[0]
    assert any(line.startswith("없는 구간:") and "face_landmarks" in line for line in lines)
    assert lines[-1] == "영역 자리 기다림: 0.2초"
