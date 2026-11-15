import json

import numpy as np

from app.tasks.area.parts.area_color import AreaColor, color_record, median_color
from tools import makeup_effect_report as report

SKIN = (232, 192, 172)
BLUSH = (235, 150, 150)
LIGHT_BLUSH = (234, 175, 165)
BROW = (150, 110, 100)


def color(rgb):
    return median_color(np.array([rgb], dtype=np.uint8))


def record(sub_step_id, region, applied, mirrored=False, reason=None):
    if reason:
        area = AreaColor(reason=reason)
    else:
        area = AreaColor(
            applied=color(applied),
            before=color(SKIN),
            skin=color(SKIN),
            skin_before=color(SKIN),
            cells=100,
        )
    return {"subStepId": sub_step_id, "region": region, "mirrored": mirrored, **color_record(area)}


def write_colors(folder, steps, video_id="sample"):
    (folder / "output").mkdir(parents=True, exist_ok=True)
    (folder / report.COLORS_FILE).write_text(
        json.dumps({"videoId": video_id, "steps": steps}), encoding="utf-8"
    )


def sample_steps():
    return [
        {
            "stepId": "s1",
            "makeup": "blush",
            "colors": [
                record("s1-1", "leftCheek", BLUSH),
                record("s1-1", "rightCheek", LIGHT_BLUSH),
                record("s1-1", None, BLUSH),
            ],
        },
        {
            "stepId": "s2",
            "makeup": "brow",
            "colors": [
                record("s2-1", "leftBrow", BROW, mirrored=True),
                record("s2-1", "rightBrow", BROW),
            ],
        },
        {
            "stepId": "s3",
            "makeup": "highlight",
            "colors": [record("s3-1", None, None, reason="noArea")],
        },
    ]


def test_effect_rows_skip_mirrored_and_missing(tmp_path) -> None:
    """뒤집어 쓴 쪽은 화장 색이 아니고 못 뽑은 줄은 값이 없다.

    표에 들어가면 부위 진하기가 틀어진다.
    """
    write_colors(tmp_path, sample_steps())

    rows = report.effect_rows(tmp_path)

    assert [(row["subStepId"], row["region"]) for row in rows] == [
        ("s1-1", "leftCheek"),
        ("s1-1", "rightCheek"),
        ("s1-1", None),
        ("s2-1", "rightBrow"),
    ]
    assert all(row["effect"]["strength"] > 0 for row in rows)


def test_representative_prefers_combined_row(tmp_path) -> None:
    """부위 표가 좌우를 두 번 세면 안 된다.

    하위 단계마다 합친 줄(없으면 한쪽 줄) 하나만 고르는지 본다.
    """
    write_colors(tmp_path, sample_steps())

    picked = report.representative(report.effect_rows(tmp_path))

    assert [(row["subStepId"], row["region"]) for row in picked] == [
        ("s1-1", None),
        ("s2-1", "rightBrow"),
    ]


def test_makeup_summary_gives_range_and_direction(tmp_path) -> None:
    """부위 표의 순서·줄 수·방향·범위가 맞는지 본다. 기준 진하기 표가 이 값으로 만들어진다."""
    write_colors(tmp_path, sample_steps())

    summary = report.makeup_summary(report.effect_rows(tmp_path))

    assert [one["makeup"] for one in summary] == ["brow", "blush"]
    assert summary[0]["direction"] == "darker"
    assert summary[0]["rows"] == 1
    assert summary[1]["min"] <= summary[1]["median"] <= summary[1]["max"]


def test_main_writes_table_chart_and_json(tmp_path, monkeypatch) -> None:
    """실행하면 표·그림·json 세 파일이 생기고 표에 줄 표와 부위 표가 다 들어가는지 본다."""
    write_colors(tmp_path, sample_steps())
    monkeypatch.setattr("sys.argv", ["makeup_effect_report.py", str(tmp_path)])

    report.main()

    text = (tmp_path / report.TABLE_FILE).read_text(encoding="utf-8")
    assert "| sample | s1-1 | blush | 찾은 쪽 합침 |" in text
    assert "| brow | 1 |" in text
    assert (tmp_path / report.CHART_FILE).stat().st_size > 0
    saved = json.loads((tmp_path / report.EFFECTS_FILE).read_text(encoding="utf-8"))
    assert len(saved) == 4


def test_main_merges_several_sample_folders(tmp_path, monkeypatch) -> None:
    """영상 여러 편을 한 표에 모으고 결과는 첫 폴더에만 쓰는지 본다."""
    first, second = tmp_path / "a", tmp_path / "b"
    write_colors(first, sample_steps(), "first")
    write_colors(second, sample_steps()[:1], "second")
    monkeypatch.setattr("sys.argv", ["makeup_effect_report.py", str(first), str(second)])

    report.main()

    saved = json.loads((first / report.EFFECTS_FILE).read_text(encoding="utf-8"))
    assert {row["videoId"] for row in saved} == {"first", "second"}
    assert not (second / report.EFFECTS_FILE).exists()
