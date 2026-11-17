"""FE가 shared/gauge 시험 데이터로 낸 값이 기대값과 같은지 본다.

FE는 시험 데이터 파일마다 사례 이름 → 그 사례의 expected와 같은 모양으로 계산한 값을 JSON으로 낸다.
  {"measure": {"lipSameAmount": {...}, …}, "stability": {"frames": {…}, "windows": {…},
   "sequences": {…}}, "substitute": {…}, "pipeline": {…}}
없는 파일 · 묶음은 건너뛰고, 있는 묶음은 모든 사례가 있어야 한다.
숫자는 허용 오차 안이면 같다고 본다. 계산만 하는 시험(measure · stability · substitute)은
ARITHMETIC이다. 기대값을 소수 넷째 자리로 반올림해 두어, 반올림 경계(예: 70.79825)에서 맞게 짠
FE가 넷째 자리 하나 다를 수 있다. 사진부터 하는 시험(pipeline)은 pipeline.v1.json의
tolerance(이름별)다.
참 · 거짓 · 글자 · null은 똑같아야 한다. 다만 hue · chroma 기대값이 「비슷」 경계(measure.v1.json
color.hueSameDegrees · chromaSame)에서 허용 오차 안이면 hueSame · chromaSame은 어느 쪽이어도 맞다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/check_fe_readings.py <FE 결과.json>
틀린 곳을 한 줄씩 적고, 모두 같으면 0, 하나라도 다르면 1로 끝난다.
"""

import argparse
import json
import math
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

SHARED = Path(__file__).resolve().parents[3] / "shared" / "gauge"
ARITHMETIC = 1e-4
GROUPS = {
    "measure": ("cases",),
    "substitute": ("cases",),
    "stability": ("frames", "windows", "sequences"),
    "pipeline": ("cases",),
}
PIPELINE_KEYS = {
    "ratio": "ratio",
    "bar": "bar",
    "hue": "hue",
    "chroma": "chroma",
    "target": "target",
    "white": "white",
    "start": "lab",
    "now": "lab",
    "before": "lab",
    "after": "lab",
    "whitePoints": "cells",
    "baselineCells": "cells",
    "madeCells": "cells",
    "cells": "cells",
}


def differences(
    expected: object, got: object, path: str, tolerance: Mapping[str, float] | float, key: str = ""
) -> Iterator[str]:
    """expected와 got이 다른 곳마다 「자리: 기대값 · 받은 값」 한 줄."""
    if isinstance(expected, Mapping):
        if not isinstance(got, Mapping):
            yield f"{path}: {expected!r} · {got!r}"
            return
        loose = _near_same_bound(expected, tolerance)
        for name, value in expected.items():
            if name not in got:
                yield f"{path}.{name}: 없음"
                continue
            if name in loose:
                continue
            yield from differences(value, got[name], f"{path}.{name}", tolerance, name)
        return
    if isinstance(expected, list):
        if not isinstance(got, list) or len(got) != len(expected):
            yield f"{path}: 길이 {len(expected)} · {got!r}"
            return
        for index, (a, b) in enumerate(zip(expected, got, strict=True)):
            yield from differences(a, b, f"{path}[{index}]", tolerance, key)
        return
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if expected != got:
            yield f"{path}: {expected!r} · {got!r}"
        return
    if not isinstance(got, (int, float)) or isinstance(got, bool) or math.isnan(got):
        yield f"{path}: {expected!r} · {got!r}"
        return
    limit = tolerance if isinstance(tolerance, float) else tolerance[PIPELINE_KEYS.get(key, "lab")]
    if abs(float(expected) - float(got)) > limit:
        yield f"{path}: {expected!r} · {got!r} (허용 {limit:g})"


def _near_same_bound(expected: Mapping, tolerance: Mapping[str, float] | float) -> set[str]:
    """「비슷」 경계에서 허용 오차 안에 있는 색감이면 hueSame · chromaSame은 어느 쪽이어도 맞다."""
    color = json.loads((SHARED / "measure.v1.json").read_text(encoding="utf-8"))["color"]
    loose = set()
    for value, flag, bound in (
        ("hue", "hueSame", color["hueSameDegrees"]),
        ("chroma", "chromaSame", color["chromaSame"]),
    ):
        number = expected.get(value)
        if flag not in expected or not isinstance(number, (int, float)):
            continue
        limit = tolerance if isinstance(tolerance, float) else tolerance[value]
        if abs(abs(number) - bound) <= limit:
            loose.add(flag)
    return loose


def check(readings: Mapping[str, Mapping]) -> list[str]:
    """FE 결과 전체를 shared/gauge 시험 데이터와 견준 틀린 곳 목록."""
    out: list[str] = []
    for name, groups in GROUPS.items():
        if name not in readings:
            continue
        spec = json.loads((SHARED / f"{name}.v1.json").read_text(encoding="utf-8"))
        tolerance = spec["tolerance"] if name == "pipeline" else ARITHMETIC
        given = readings[name]
        for group in groups:
            cases: Sequence[Mapping] = spec[group]
            answers = given if group == "cases" else given.get(group)
            if answers is None:
                continue
            for case in cases:
                where = f"{name}.{group}.{case['name']}"
                if case["name"] not in answers:
                    out.append(f"{where}: 없음")
                    continue
                out.extend(differences(case["expected"], answers[case["name"]], where, tolerance))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("readings", type=Path)
    args = parser.parse_args(argv)
    wrong = check(json.loads(args.readings.read_text(encoding="utf-8")))
    for line in wrong:
        print(line)
    print("모두 같음" if not wrong else f"다른 곳 {len(wrong)}개")
    return 0 if not wrong else 1


if __name__ == "__main__":
    sys.exit(main())
