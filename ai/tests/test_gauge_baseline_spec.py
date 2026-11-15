import json

import jsonschema
import numpy as np

from tools.gauge import baseline as bl
from tools.gauge.export_baseline_spec import SPEC_PATH, spec

SCHEMA_PATH = SPEC_PATH.with_name("baseline.v1.schema.json")


def test_shared_spec_matches_python_baseline():
    """FE가 읽는 값·칸 표가 파이썬 기준 구현과 같아야 두 쪽이 같은 숫자를 낸다.

    baseline.py를 고친 뒤 tools/gauge/export_baseline_spec.py를 다시 돌리지 않으면 여기서 걸린다.
    """
    assert json.loads(SPEC_PATH.read_text(encoding="utf-8")) == spec()


def test_shared_spec_passes_its_schema():
    """공유 파일이 shared/gauge의 JSON Schema를 통과해야 FE가 형식을 믿고 읽는다."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(json.loads(SPEC_PATH.read_text(encoding="utf-8")), schema)


def test_cell_rows_round_trip_to_cells():
    """칸 표 글자를 다시 칸으로 바꾸면 맨피부 칸은 재는 칸 안에 있어야 한다."""
    data = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    measured = np.array([[c == "1" for c in row] for row in data["cells"]["measured"]])
    skin = np.array([[c == "1" for c in row] for row in data["cells"]["skin"]])
    assert measured.shape == (bl.GRID, bl.GRID)
    assert not (skin & ~measured).any()
    assert skin.sum() > 0.5 * measured.sum()
