"""shared/gauge 규격 파일끼리 같은 값을 같게 적었는지 본다.

FE는 파일마다 따로 읽는다. 같은 값(칸 수 · 막대 · 재는 간격 · 검정 갈색 화장)이 파일마다 다르면
FE가 어느 쪽을 쓰느냐에 따라 게이지가 달라진다.
"""

import json
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parents[2] / "shared" / "gauge"
FILES = ("baseline", "measure", "stability", "substitute")


def load(name: str) -> dict:
    return json.loads((SHARED / f"{name}.v1.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def specs() -> dict[str, dict]:
    return {name: load(name) for name in FILES}


def test_every_spec_file_is_listed_in_the_readme():
    readme = (SHARED / "README.md").read_text(encoding="utf-8")

    for path in sorted(SHARED.glob("*.json")):
        assert f"`{path.name}`" in readme, path.name


def test_grid_is_the_same_in_baseline_and_measure(specs):
    assert specs["baseline"]["grid"] == specs["measure"]["grid"]


def test_bar_is_the_same_in_measure_and_substitute(specs):
    assert specs["measure"]["bar"] == specs["substitute"]["bar"]


def test_timing_is_the_same_in_measure_and_stability(specs):
    assert specs["measure"]["frames"] == specs["stability"]["window"]


def test_dark_makeups_are_the_same_in_measure_and_substitute(specs):
    assert specs["measure"]["methods"]["darkMakeups"] == specs["substitute"]["color"]["darkMakeups"]


def test_stability_label_bounds_sit_around_the_reference_line(specs):
    low, high = specs["stability"]["labels"]["bounds"]

    assert low < 1.0 < high
