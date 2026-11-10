import copy
import json
from pathlib import Path

import pytest

from tools.ops_guide_job_check import check, part_table, photo_counts, report_lines

AREA_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_area.json"
NO_SPANS = {"spans": []}


@pytest.fixture
def body():
    """저장소 샘플 영역(19단계, 네 상태가 다 있음)에 같은 단계의 설명을 붙인 정상 콜백 본문."""
    area = json.loads(AREA_SAMPLE.read_text(encoding="utf-8"))
    guide = {
        "steps": [
            {"stepId": step["stepId"], "order": step["order"], "actions": [], "doneWhen": None}
            for step in area["steps"]
        ]
    }
    return {
        "jobId": "job-1",
        "videoId": area["videoId"],
        "status": "COMPLETED",
        "guide": guide,
        "area": area,
        "error": None,
    }


def sub_step(body, step_id):
    step = next(step for step in body["area"]["steps"] if step["stepId"] == step_id)
    return step["subSteps"][0]


def test_sample_result_passes_all_checks(body):
    """멀쩡한 결과를 틀렸다고 하면 운영 결과에서 나온 걸림을 믿을 수 없다."""
    report = check(body, NO_SPANS)

    assert report["schemaErrors"] == []
    assert report["ruleErrors"] == []
    assert report["stepMatchErrors"] == []
    assert report["stepCount"] == 19


def test_unknown_status_is_caught_by_schema(body):
    """정해진 네 상태가 아닌 값은 칸 하나만 봐도 틀린 것이라 양식 검사가 잡아야 한다."""
    sub_step(body, "s5")["status"] = "found"

    report = check(body, NO_SPANS)

    assert report["schemaErrors"]
    assert any("area.steps[4](s5).subSteps[0].status" in line for line in report["schemaErrors"])


def test_template_without_key_passes_schema_but_breaks_rule(body):
    """기본 영역인데 키가 비면 칸마다는 맞아 양식은 통과하고, 칸끼리 규칙에서만 걸린다.

    두 검사를 따로 두는 이유가 이 경우다.
    """
    sub_step(body, "s5")["templateId"] = None

    report = check(body, NO_SPANS)

    assert report["schemaErrors"] == []
    assert any("s5" in line and "templateId" in line for line in report["ruleErrors"])


def test_mascara_not_applicable_breaks_rule(body):
    """11-04 운영 결과에서 실제로 본 경우다. 해당 없음은 기타에만 쓴다는 규칙에 걸려야 한다."""
    mascara = sub_step(body, "s14")
    mascara.update(status="notApplicable", reasons=[], templateId=None)

    report = check(body, NO_SPANS)

    assert report["schemaErrors"] == []
    assert any("s14" in line for line in report["ruleErrors"])


def test_missing_explained_step_is_reported(body):
    """설명에서 단계가 빠지면 FE가 그 단계의 설명과 영역을 짝지을 수 없다."""
    body["guide"]["steps"] = [step for step in body["guide"]["steps"] if step["stepId"] != "s7"]

    report = check(body, NO_SPANS)

    assert report["stepMatchErrors"] == ["영역에만 있는 단계: s7"]
    assert "단계 맞춤: 1곳 걸림" in report_lines(report)


def test_reordered_steps_are_reported(body):
    """빠진 단계 없이 순서만 바뀌어도 화면에서 설명과 영역이 엇갈린다."""
    steps = body["guide"]["steps"]
    steps[0], steps[1] = steps[1], steps[0]

    assert check(body, NO_SPANS)["stepMatchErrors"] == ["설명과 영역의 단계 순서가 다릅니다"]


def test_part_table_splits_not_analyzed_from_not_found(body):
    """기본 영역은 분석하지 않는 부위와 분석했지만 못 찾은 부위로 나눠야 원인을 가를 수 있다."""
    parts = {row["makeup"]: row for row in part_table(body)}

    assert parts["mascara"]["templateNotAnalyzed"] == 1
    assert parts["mascara"]["templateNotFound"] == 0
    assert parts["blush"]["templateNotFound"] == 2
    assert parts["blush"]["reasons"] == {"noUsableFrame": 2}
    assert (parts["lip"]["extracted"], parts["lip"]["templateNotFound"]) == (1, 1)
    assert parts["lip"]["failed"] == 1
    assert parts["lip"]["reasons"] == {"analysisError": 1, "noUsableFrame": 1}
    assert parts["other"]["notApplicable"] == 6
    assert parts["brow"]["steps"] == 0


def test_photo_counts_come_from_spans():
    """사진 오류는 콜백에 없고 구간 기록에만 있어, 영역 결과와 따로 센다."""
    spans = {
        "spans": [
            {"name": "download_frames", "input": {"frames": 10}, "output": {"missing": 1}},
            {"name": "face_landmarks", "input": {}, "output": {"ok": 7, "noFace": 2}},
            {"name": "check_frames", "input": {}, "output": {"ok": 5, "noFace": 2, "rejected": 2}},
        ]
    }

    photos = photo_counts(spans)

    assert photos == {
        "frames": 10,
        "missing": 1,
        "landmarks": {"ok": 7, "noFace": 2},
        "checked": {"ok": 5, "noFace": 2, "rejected": 2},
    }


def test_check_does_not_change_body(body):
    """받은 결과 파일 내용을 검사하다 바꾸면 다음 검사와 문서가 달라진다."""
    before = copy.deepcopy(body)

    check(body, NO_SPANS)

    assert body == before
