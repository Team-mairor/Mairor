"""지표 도구를 기준값을 바꿔 돌리고(빠른 판) 그 결과를 따로 두는 옵션을 다룬다 (개발용).

--set <모듈>.<상수>=<값>은 서비스 부위 코드의 상수를 바꾼다. 모듈은 app/tasks/area/parts의 파일
이름(MODULES)이고 여러 번 줄 수 있다. 값은 파이썬 글자(1.2, 3, True, (0.8, 1.2))로 쓴다.
숫자 상수에는 정수·소수를 모두 받는다(코드에 1로 적힌 붉어짐 기준을 1.2로 바꿔 볼 수 있게).
소수 자리에 정수를 주면 소수로, 정수 자리에 3.0처럼 딱 떨어지는 소수를 주면 정수로 받는다.
칸 수처럼 정수여야 하는 상수에 3.5 같은 소수를 넣으면 도구가 돌다 오류로 멈춘다.
참·거짓 상수는 참·거짓만, 묶음 상수는 같은 길이 묶음만 받는다.
지표 도구는 시작할 때 일부 상수를 부위 표(PARTS)에 복사하므로 --set은 도구를 불러오기 전에 바꿔야
한다. 그래서 도구에 직접 주지 않고 tools/run_metric.py나 tools/profile_metrics.py로 준다.
--tag <이름>은 결과를 output/occlusion/<가림 표 이름>/<이름>/(가림 표가 없으면 output/<이름>/)에
따로 둔다. 기준 결과를 덮지 않게, --set을 주면 --tag도 꼭 줘야 한다. 바꾼 상수는 그 폴더의
settings.json에 적는다. 대표 지도 저장(tools/face_map_store.py)은 이 상수 대부분과 상관없어
저장한 것을 그대로 꺼내 쓰고, 범위나 대표 지도 상수가 바뀌면 새로 만든다.
--parts <부위,부위>는 도구가 그 부위만 계산하게 한다. 일꾼 여러 명이 (도구, 부위) 일거리를 나눠
돌린 뒤(tools/run_metrics.py) 부위 순서대로 이어 붙이면(merge_results) 한 번에 돈 결과와 같다.
네 지표 도구는 결과를 write_result 한 가지 형식으로 써서, 이어 붙인 결과도 같은 바이트가 된다.
"""

import ast
import importlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

PARTS_PACKAGE = "app.tasks.area.parts"
MODULES = (
    "area_preparation",
    "blush_area",
    "brow_area",
    "eyeliner_area",
    "eyeshadow_area",
    "lip_area",
)
SET_OPTION = "--set"
TAG_OPTION = "--tag"
PARTS_OPTION = "--parts"
PARTS_USAGE = f"[{PARTS_OPTION} <부위,부위>]"
SETTINGS_USAGE = f"[{SET_OPTION} <모듈>.<상수>=<값> ...] [{TAG_OPTION} <이름>]"
TAG_USAGE = f"[{TAG_OPTION} <이름>]"
SETTINGS_FILE = "settings.json"
CONSTANT_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
TAG_NAME = re.compile(r"[A-Za-z0-9_-]+")
SHIFT_ENV = "GUIDE_METRIC_STEP_SHIFT_MS"


@dataclass(frozen=True)
class Setting:
    """바꾼 상수 하나. before는 바꾸기 전 값이다."""

    module: str
    name: str
    value: Any
    before: Any


def shifted_reference(reference: Any) -> Any:
    """환경 변수 GUIDE_METRIC_STEP_SHIFT_MS만큼 모든 단계의 시작·끝을 옮긴 입력을 돌려준다.

    값이 없거나 0이면 받은 입력 그대로다. 같은 코드로 사진 창만 조금 옮겨 다시 재서
    지표가 얼마나 흔들리는지(측정 흔들림) 볼 때 쓴다. 환경 변수라 tools/run_metrics.py가 띄우는
    일거리에도 그대로 전해진다.
    """
    shift = int(os.environ.get(SHIFT_ENV, "0")) / 1000
    if not shift:
        return reference
    steps = [
        step.model_copy(
            update={
                "start_seconds": step.start_seconds + shift,
                "end_seconds": step.end_seconds + shift,
            }
        )
        for step in reference.manifest.steps
    ]
    return replace(reference, manifest=reference.manifest.model_copy(update={"steps": steps}))


def take_option(args: Sequence[str], option: str) -> tuple[list[str], list[str]]:
    """인자에서 option <값> 짝을 모두 떼어 (나머지 인자, 값들)을 돌려준다. 값이 없으면 끝낸다."""
    rest, values = [], []
    items = iter(args)
    for arg in items:
        if arg != option:
            rest.append(arg)
            continue
        value = next(items, None)
        if value is None:
            raise SystemExit(f"{option} 뒤에 값이 없습니다")
        values.append(value)
    return rest, values


def split_settings(args: Sequence[str]) -> tuple[list[str], list[str]]:
    """인자에서 --set <모듈>.<상수>=<값>을 모두 떼어 (나머지 인자, 바꿀 글자들)을 돌려준다."""
    return take_option(args, SET_OPTION)


def split_tag(args: Sequence[str]) -> tuple[list[str], str | None]:
    """인자에서 --tag <이름>을 떼어 (나머지 인자, 이름)을 돌려준다. 이름은 글자·숫자·_·-만 된다."""
    rest, tags = take_option(args, TAG_OPTION)
    if len(tags) > 1:
        raise SystemExit(f"{TAG_OPTION}는 한 번만 줄 수 있습니다")
    if tags and not TAG_NAME.fullmatch(tags[0]):
        raise SystemExit(f"{TAG_OPTION} 이름은 글자·숫자·_·-만 됩니다: {tags[0]}")
    return rest, tags[0] if tags else None


def tagged_dir(base: Path, tag: str | None) -> Path:
    """결과 폴더. tag가 있으면 base 아래 tag 폴더다."""
    return base if tag is None else base / tag


def converted(before: Any, value: Any) -> Any:
    """value를 before와 맞는 종류로 바꾼다. 맞출 수 없으면 None이다.

    숫자끼리는 서로 받는다. 소수 자리의 정수는 소수로, 정수 자리의 딱 떨어지는 소수는 정수로 바꾼다.
    튜플은 같은 길이, dict(자리마다 값 등)는 같은 키일 때 칸마다 맞춘다.
    방식 이름 같은 글자 상수에는 글자만 받는다.
    """
    if isinstance(before, bool) or isinstance(value, bool):
        return value if isinstance(before, bool) and isinstance(value, bool) else None
    if isinstance(before, str) or isinstance(value, str):
        return value if isinstance(before, str) and isinstance(value, str) else None
    if isinstance(before, int | float):
        if not isinstance(value, int | float):
            return None
        if isinstance(before, float):
            return float(value)
        return int(value) if float(value).is_integer() else value
    if isinstance(before, tuple) and isinstance(value, tuple) and len(before) == len(value):
        items = [converted(old, new) for old, new in zip(before, value, strict=True)]
        return None if any(item is None for item in items) else tuple(items)
    if isinstance(before, dict) and isinstance(value, dict) and before.keys() == value.keys():
        pairs = {key: converted(before[key], value[key]) for key in before}
        return None if any(item is None for item in pairs.values()) else pairs
    return None


def parse_setting(text: str) -> tuple[str, str, Any]:
    """<모듈>.<상수>=<값> 글자를 (모듈, 상수, 값)으로 나눈다. 모양이 틀리면 끝낸다."""
    target, sep, raw = text.partition("=")
    module, dot, name = target.strip().rpartition(".")
    if not sep or not dot or module not in MODULES or not CONSTANT_NAME.fullmatch(name):
        raise SystemExit(
            f"{SET_OPTION} 모양이 틀렸습니다: {text} (예: eyeshadow_area.REDDENING_MIN=1.2, "
            f"모듈은 {', '.join(MODULES)})"
        )
    try:
        value = ast.literal_eval(raw.strip())
    except (ValueError, SyntaxError) as error:
        raise SystemExit(f"{SET_OPTION} 값을 읽지 못했습니다: {text}") from error
    return module, name, value


def apply_settings(texts: Sequence[str]) -> list[Setting]:
    """--set 글자들을 차례로 서비스 모듈 상수에 넣고, 바꾼 것들을 돌려준다.

    없는 상수이거나 원래 값과 종류가 다르면 아무것도 바꾸지 않고 끝낸다.
    """
    planned = []
    for text in texts:
        module_name, name, value = parse_setting(text)
        module = importlib.import_module(f"{PARTS_PACKAGE}.{module_name}")
        if not hasattr(module, name):
            raise SystemExit(f"{module_name}에 {name} 상수가 없습니다")
        before = getattr(module, name)
        value_as = converted(before, value)
        if value_as is None:
            raise SystemExit(
                f"{module_name}.{name}은 {type(before).__name__}({before!r})인데"
                f" {value!r}를 받았습니다"
            )
        planned.append((module, Setting(module_name, name, value_as, before)))
    for module, setting in planned:
        setattr(module, setting.name, setting.value)
    return [setting for _, setting in planned]


def write_settings(
    folder: Path, tool: str, args: Sequence[str], settings: Sequence[Setting]
) -> Path:
    """결과 폴더에 어떤 도구를 어떤 인자와 바꾼 상수로 돌렸는지 settings.json으로 적는다."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SETTINGS_FILE
    doc = {
        "tool": tool,
        "args": list(args),
        "settings": [
            {"module": s.module, "name": s.name, "value": s.value, "before": s.before}
            for s in settings
        ],
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def split_parts(args: Sequence[str]) -> tuple[list[str], list[str] | None]:
    """인자에서 --parts <부위,부위>를 떼어 (나머지 인자, 부위 이름들)을 돌려준다.

    --parts가 없으면 부위 이름 자리는 None이다.
    """
    rest, values = take_option(args, PARTS_OPTION)
    if len(values) > 1:
        raise SystemExit(f"{PARTS_OPTION}는 한 번만 줄 수 있습니다")
    if not values:
        return rest, None
    names = [name.strip() for name in values[0].split(",") if name.strip()]
    if not names:
        raise SystemExit(f"{PARTS_OPTION} 뒤에 부위 이름이 없습니다")
    return rest, names


def selected_parts(parts: Sequence[Any], names: Sequence[str] | None) -> list[Any]:
    """도구의 부위 표에서 names에 든 부위만 원래 순서대로 고른다. names가 None이면 전부다.

    부위 표에 없는 이름이 있으면 끝낸다. 부위는 name 속성으로 알아본다.
    """
    if names is None:
        return list(parts)
    known = [part.name for part in parts]
    unknown = [name for name in names if name not in known]
    if unknown:
        raise SystemExit(f"없는 부위입니다: {', '.join(unknown)} (있는 부위: {', '.join(known)})")
    return [part for part in parts if part.name in names]


def write_result(path: Path, doc: dict) -> None:
    """지표 도구 결과를 path에 쓴다. 네 도구와 합친 결과가 모두 이 한 가지 형식으로 쓴다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def merge_results(docs: Sequence[dict]) -> dict:
    """부위별로 나눠 계산한 결과들을 부위 순서대로 이어 붙인다. docs는 부위 순서대로 받는다.

    목록 칸(줄들)은 차례로 이어 붙이고, 목록이 아닌 칸(영상 이름·설정값)은 모두 같아야 한다.
    칸 이름이나 목록이 아닌 칸이 일거리마다 다르면, 다른 조건으로 돈 결과라 끝낸다.
    """
    if not docs:
        raise SystemExit("합칠 결과가 없습니다")
    keys = list(docs[0])
    if any(list(doc) != keys for doc in docs):
        raise SystemExit("일거리마다 결과 칸 이름이 다릅니다")
    merged: dict = {}
    for key in keys:
        values = [doc[key] for doc in docs]
        if all(isinstance(value, list) for value in values):
            merged[key] = [item for value in values for item in value]
        elif all(value == values[0] for value in values):
            merged[key] = values[0]
        else:
            raise SystemExit(f"일거리마다 {key} 칸이 다릅니다")
    return merged
