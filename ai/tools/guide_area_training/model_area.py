"""바른 곳 찾기 모델(train.py)을 서비스 부위 코드 자리에 끼워, 규칙과 같은 길로 재게 한다(개발용).

서비스 부위 코드(find_*_area)는 사진을 골라 직전·직후 얼굴 지도를 만든 뒤 지도 함수로 색 변화를
재고 판정 함수(check_*)로 바른 칸을 정한다. install(method, model)은 그 판정 자리만 바꿔, 사진
고르기·지도 만들기·좌우 맞추기·테두리는 서비스 그대로 두고 칸 찾기만 모델(또는 모델과 규칙을
합친 것)로 한다.
- model: 모델이 그 자리 번호로 칠한 칸. 얼굴 밖 칸과 모름 칸은 지우고, 부위의 MIN_PIECE_CELLS
  보다 작은 조각은 서비스처럼 버린다.
- and: 규칙과 모델이 둘 다 칠한 칸. or: 둘 중 하나라도 칠한 칸.
- rule_gate: 규칙이 찾았을 때만 모델 모양. model_gate: 모델이 찾았을 때만 규칙 모양(규칙이 못
  찾았으면 모델 모양).
모델은 onnx(export_onnx)로 돌린다. 서비스도 학습 프레임워크 없이 onnxruntime으로 돌리기 때문이다.
짝 부위의 쪽은 지도 가운데 선(boundary_metric.side_half)으로 나눈다. 자리 번호에 좌우가 없어서다.
환경 변수 A306_METHOD·A306_MODEL이 있으면 sitecustomize에서 install을 불러, 지표 도구가 일거리마다
띄우는 하위 프로세스에도 같은 방식이 들어간다.
"""

import hashlib
import os
import sys
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import labels  # noqa: E402

from app.tasks.area.common.face_map import MAP_SIZE, face_cells  # noqa: E402
from app.tasks.area.parts import (  # noqa: E402
    blush_area,
    brow_area,
    eyeliner_area,
    eyeshadow_area,
    lip_area,
)

METHODS = ("model", "and", "or", "rule_gate", "model_gate")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
CLASS_IDS = labels.CLASS_IDS
MIN_PIECE = {
    "lip": lip_area.MIN_PIECE_CELLS,
    "eyeshadow": eyeshadow_area.MIN_PIECE_CELLS,
    "eyeliner": eyeliner_area.MIN_PIECE_CELLS,
}


def export_onnx(checkpoint: Path, out: Path) -> None:
    """train.py로 학습한 BiSeNet 가중치를 onnx로 바꾼다. 주 출력(첫 머리)의 자리별 점수만 낸다."""
    import torch
    import train

    model = train.load_trained("bisenet", checkpoint, "cpu")

    class Head(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.inner = model

        def forward(self, x):
            return self.inner(x)[0]

    dummy = torch.zeros(1, 6, MAP_SIZE, MAP_SIZE)
    torch.onnx.export(
        Head().eval(),
        dummy,
        str(out),
        input_names=["maps"],
        output_names=["scores"],
        opset_version=17,
        dynamo=False,
    )


class OnnxModel:
    """onnx 모델 하나. predict는 전후 지도에서 칸마다 자리 번호를 낸다(얼굴 밖은 0)."""

    def __init__(self, path: Path, threads: int | None = None, store: Path | None = None) -> None:
        import onnxruntime

        options = onnxruntime.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
            options.inter_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.cache: dict[str, np.ndarray] = {}
        self.store = None if store is None else store / path.stem
        if self.store is not None:
            self.store.mkdir(parents=True, exist_ok=True)

    def predict(self, before: np.ndarray, after: np.ndarray) -> np.ndarray:
        """같은 전후 지도는 한 번만 계산한다. store가 있으면 결과를 파일로 남겨 같이 쓴다."""
        key = hashlib.blake2b(before.tobytes() + after.tobytes(), digest_size=16).hexdigest()
        if key in self.cache:
            return self.cache[key]
        saved = None if self.store is None else self.store / f"{key}.npz"
        if saved is not None and saved.is_file():
            classes = np.load(saved)["classes"]
        else:
            maps = np.concatenate([before, after], axis=2).astype(np.float32) / 255.0
            x = ((maps - np.tile(MEAN, 2)) / np.tile(STD, 2)).transpose(2, 0, 1)[None]
            scores = self.session.run(None, {"maps": x.astype(np.float32)})[0][0]
            classes = scores.argmax(0).astype(np.uint8)
            classes[~face_cells()] = 0
            if saved is not None:
                partial = saved.with_name(f"{key}.{os.getpid()}.tmp.npz")
                np.savez_compressed(partial, classes=classes)
                os.replace(partial, saved)
        if len(self.cache) > 64:
            self.cache.clear()
        self.cache[key] = classes
        return classes


@lru_cache
def side_half(side: str) -> np.ndarray:
    from tools.boundary_metric import side_half as half

    return half(side)


def drop_small(mask: np.ndarray, makeup: str) -> np.ndarray:
    """부위의 MIN_PIECE_CELLS보다 작은 조각을 버린다. 기준이 없는 부위는 그대로다."""
    least = MIN_PIECE.get(makeup)
    if least is None or not mask.any():
        return mask
    count, pieces, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    keep = np.zeros(count, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= least
    return keep[pieces]


def class_mask(
    classes: np.ndarray, name: str, makeup: str, side: str | None, unknown: np.ndarray | None
) -> np.ndarray | None:
    mask = classes == CLASS_IDS[name]
    if unknown is not None:
        mask &= ~unknown
    if side is not None:
        mask &= side_half(side)
    mask = drop_small(mask, makeup)
    return mask if mask.any() else None


def combine(method: str, rule: np.ndarray | None, model: np.ndarray | None) -> np.ndarray | None:
    """규칙 칸과 모델 칸을 방식대로 합친다. 비면 None(못 찾음)이다."""
    if method == "model":
        out = model
    elif method == "and":
        out = None if rule is None or model is None else rule & model
    elif method == "or":
        out = model if rule is None else rule if model is None else rule | model
    elif method == "rule_gate":
        out = model if rule is not None else None
    elif method == "model_gate":
        out = (rule if rule is not None else model) if model is not None else None
    else:
        raise ValueError(method)
    return out if out is not None and out.any() else None


class MapMemory:
    """지도 함수가 낸 규칙 값(색 변화 표 등)을 만든 전후 지도를 기억해 판정 함수가 꺼내 쓰게 한다.

    지도 함수는 규칙 값을 그대로 돌려줘야 한다. 지표 도구(noise_metric·timing_metric)가 그 값을
    숫자 표로 바로 쓰기 때문이다. 값 객체 자체를 열쇠로 최근 size개만 기억한다.
    """

    def __init__(self, size: int = 16) -> None:
        self.size = size
        self.items: dict[int, tuple[object, np.ndarray, np.ndarray]] = {}

    def keep(self, value: object, before: np.ndarray, after: np.ndarray) -> object:
        self.items.pop(id(value), None)
        self.items[id(value)] = (value, before, after)
        while len(self.items) > self.size:
            self.items.pop(next(iter(self.items)))
        return value

    def maps(self, value: object) -> tuple[np.ndarray, np.ndarray]:
        """value를 만든 (직전 지도, 직후 지도). 지도 함수를 거치지 않은 값이면 LookupError다."""
        item = self.items.get(id(value))
        if item is None or item[0] is not value:
            raise LookupError("지도 함수(install로 바꾼 것)가 만들지 않은 값입니다.")
        return item[1], item[2]


def install(
    method: str, model_path: Path, threads: int | None = None, store: Path | None = None
) -> None:
    """부위 코드의 판정 함수를 method 방식으로 바꾼다. 같은 프로세스에서 한 번만 부른다.

    지도 함수(lip_area_on_maps·blush_reddening·brow_darkening·eyeshadow_reddening·zone_change)는
    규칙 값을 그대로 돌려주고 그 값을 만든 전후 지도만 기억한다(MapMemory). 지표 도구가 지도 함수
    값을 숫자 표로 바로 쓰기 때문이다. 판정 함수(check_*)는 규칙 판정에 모델 칸을 합친다.
    규칙 판정이 noUsableFrame(살펴볼 곳의 절반 넘게 모름 칸)이면 사진 판정이라 그대로 둔다.
    모델만 찾은 섀도 자리의 세기는 자리를 모를 때의 관문(UNKNOWN_ZONE_TOP_MIN) 값으로 둔다.
    store를 주면 모델 결과를 파일로 남겨, 같은 모델로 도는 다른 방식(and·or 등)이 다시 계산하지
    않는다.
    """
    if method not in METHODS:
        raise ValueError(method)
    model = OnnxModel(model_path, threads, store)
    found_reason = {
        "lip": "lipColorNotFound",
        "blush": "blushColorNotFound",
        "brow": "browColorNotFound",
        "eyeshadow": "eyeshadowColorNotFound",
        "eyeliner": "eyelinerColorNotFound",
    }

    memory = MapMemory()

    def remembered(make: Callable) -> Callable:
        def maps(before, after, *rest, **named):
            return memory.keep(make(before, after, *rest, **named), before, after)

        return maps

    def predict(value: object) -> np.ndarray:
        return model.predict(*memory.maps(value))

    lip_check = lip_area.check_lip_area

    def lip_checked(area, unknown=None):
        rule = lip_check(area, unknown)
        if rule.reason == "noUsableFrame":
            return rule
        mask = combine(method, rule.mask, class_mask(predict(area), "lip", "lip", None, unknown))
        if mask is None:
            return lip_area.LipArea(mask=None, reason=rule.reason or found_reason["lip"])
        return lip_area.LipArea(mask=mask)

    lip_area.lip_area_on_maps = remembered(lip_area.lip_area_on_maps)
    lip_area.check_lip_area = lip_checked

    blush_check = blush_area.check_blush_area

    def blush_checked(reddening, cheek, unknown=None):
        rule = blush_check(reddening, cheek, unknown)
        if rule.reason == "noUsableFrame":
            return rule
        mask = combine(
            method, rule.mask, class_mask(predict(reddening), "blush", "blush", cheek, unknown)
        )
        if mask is None:
            return blush_area.BlushArea(
                mask=None, reason=rule.reason or found_reason["blush"], peak=rule.peak
            )
        return blush_area.BlushArea(mask=mask, peak=rule.peak)

    blush_area.blush_reddening = remembered(blush_area.blush_reddening)
    blush_area.check_blush_area = blush_checked

    brow_check = brow_area.check_brow_area

    def brow_checked(darkening, brow, unknown=None):
        rule = brow_check(darkening, brow, unknown)
        if rule.reason == "noUsableFrame":
            return rule
        mask = combine(
            method, rule.mask, class_mask(predict(darkening), "brow", "brow", brow, unknown)
        )
        if mask is None:
            return brow_area.BrowArea(
                mask=None, darkening=rule.darkening, reason=rule.reason or found_reason["brow"]
            )
        strength = rule.darkening if rule.mask is not None else float(mask.sum())
        return brow_area.BrowArea(mask=mask, darkening=strength)

    brow_area.brow_darkening = remembered(brow_area.brow_darkening)
    brow_area.check_brow_area = brow_checked

    shadow_check = eyeshadow_area.check_eyeshadow_area

    def shadow_checked(reddening, eye, unknown=None, brightening=None):
        rule = shadow_check(reddening, eye, unknown, brightening)
        if rule.reason == "noUsableFrame":
            return rule
        classes = predict(reddening)
        zones = {}
        for zone, name in (("upper", "eyeshadowUpper"), ("under", "eyeshadowUnder")):
            ruled = rule.zone(zone)
            mask = combine(method, ruled.mask, class_mask(classes, name, "eyeshadow", eye, unknown))
            if mask is None:
                zones[zone] = eyeshadow_area.ZoneArea(
                    mask=None,
                    strength=ruled.strength,
                    reason=ruled.reason or found_reason["eyeshadow"],
                )
            elif ruled.mask is not None:
                zones[zone] = eyeshadow_area.ZoneArea(
                    mask=mask, strength=ruled.strength, color=ruled.color
                )
            else:
                zones[zone] = eyeshadow_area.ZoneArea(
                    mask=mask, strength=eyeshadow_area.UNKNOWN_ZONE_TOP_MIN[zone]
                )
        union = [z.mask for z in zones.values() if z.mask is not None]
        if not union:
            return eyeshadow_area.EyeshadowArea(
                mask=None, reason=rule.reason or found_reason["eyeshadow"], zones=zones
            )
        return eyeshadow_area.EyeshadowArea(mask=np.logical_or.reduce(union), zones=zones)

    eyeshadow_area.eyeshadow_reddening = remembered(eyeshadow_area.eyeshadow_reddening)
    eyeshadow_area.check_eyeshadow_area = shadow_checked

    liner_change, liner_check = eyeliner_area.zone_change, eyeliner_area.check_eyeliner_area

    def liner_maps(before, afters, eye, before_unknown=None):
        changed, unknown = liner_change(before, afters, eye, before_unknown)
        after = afters[max(afters)][0][0]
        return memory.keep(changed, before, after), unknown

    def liner_checked(changed, eye, unknown=None):
        rule = liner_check(changed, eye, unknown)
        if rule.reason == "noUsableFrame":
            return rule
        classes = predict(changed)
        flat = unknown_union(unknown)
        zones = {}
        for zone, name in (("upper", "eyelinerUpper"), ("under", "eyelinerUnder")):
            ruled = rule.zone(zone)
            mask = combine(method, ruled.mask, class_mask(classes, name, "eyeliner", eye, flat))
            zones[zone] = eyeliner_area.ZoneLine(
                mask=mask,
                reason=None if mask is not None else ruled.reason or found_reason["eyeliner"],
            )
        union = [z.mask for z in zones.values() if z.mask is not None]
        if not union:
            return eyeliner_area.EyelinerArea(
                mask=None, reason=rule.reason or found_reason["eyeliner"], zones=zones
            )
        return eyeliner_area.EyelinerArea(mask=np.logical_or.reduce(union), zones=zones)

    eyeliner_area.zone_change, eyeliner_area.check_eyeliner_area = liner_maps, liner_checked


def install_each_side() -> None:
    """짝 부위의 좌우 맞추기를 끄고 쪽마다 찾은 모양을 그대로 쓰게 한다(좌우 방식 비교용).

    서비스는 눈썹·아이라인은 한쪽만 찾으면 뒤집어 양쪽에 쓰고, 섀도·블러셔는 두 쪽 모두 찾아야
    쓰고, 두 쪽을 찾으면 눈썹은 하나를 고르고 아이라인은 두 눈을 합친다. 모델은 쪽마다 따로
    칠하므로, 찾은 쪽에만 그 쪽 모양을 내보내는 경우도 견준다.
    짝 결과는 서비스처럼 모든 쪽을 담고 못 찾은 쪽은 빈 표로 둔다. 하위 단계를 만들 때
    (pair_sub_step·eyeliner_sub_step) 빈 쪽은 영역을 적지 않는다.
    아이라인은 앞 단계에서 안내한 칸(drawn) 빼기와 FOUND_MIN_CELLS는 그대로 둔다.
    """
    from app.tasks.area import guide_area_builder
    from tools import output_area

    def each(masks: dict) -> dict | None:
        found = {side: mask for side, mask in masks.items() if mask is not None and mask.any()}
        if not found:
            return None
        empty = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
        return {side: found.get(side, empty) for side in masks}

    original_pair = guide_area_builder.pair_sub_step

    def pair_each(sub_step_id, makeup, areas, masks, *rest):
        if masks is not None:
            areas = {side: area for side, area in areas.items() if has_cells(masks, side)}
        return original_pair(sub_step_id, makeup, areas, masks, *rest)

    def line_each(sub_step_id, masks):
        outlines = {
            eye: [
                points
                for points in guide_area_builder.smooth_outlines(
                    masks[eye],
                    eyeliner_area.OUTLINE_SMOOTH_CELLS,
                    eyeliner_area.OUTLINE_GROW_CELLS,
                    every_piece=True,
                )
                if guide_area_builder.points_to_anchors(points)
            ]
            for eye in eyeliner_area.EYES
            if has_cells(masks, eye)
        }
        outlines = {eye: lines for eye, lines in outlines.items() if lines}
        if not outlines:
            return None
        return guide_area_builder.AreaSubStep(
            sub_step_id=sub_step_id,
            order=1,
            status="extracted",
            reasons=[],
            template_id=None,
            guide_sets=[
                guide_area_builder.GuideSet(
                    region=eye,
                    source="extracted",
                    guides=[
                        guide_area_builder.PolygonShape(
                            type="polygon", outline=guide_area_builder.points_to_anchors(points)
                        )
                        for points in lines
                    ],
                    exclude=[eye] if guide_area_builder._surrounds(lines, eye) else [],
                )
                for eye, lines in outlines.items()
            ],
        )

    def brows(areas):
        return each({side: areas[side].mask for side in brow_area.BROWS})

    def cheeks(areas):
        return each({side: areas[side].mask for side in blush_area.CHEEKS})

    def shadows(areas, zone, zone_known=True):
        return each(
            {eye: areas[eye].zone(zone).mask for eye in eyeshadow_area.EYES if eye in areas}
        )

    original_liner = eyeliner_area.paired_eyeliner

    def liners(areas, zone, drawn=None):
        out = {}
        for eye in eyeliner_area.EYES:
            if eye not in areas or areas[eye].zone(zone).mask is None:
                continue
            single = original_liner({eye: areas[eye]}, zone, drawn)
            if single:
                out[eye] = single[eye] & eyeliner_area.eyeliner_range(eye, zone)
        return each(out)

    for module in (brow_area, guide_area_builder, output_area):
        if hasattr(module, "symmetric_brows"):
            module.symmetric_brows = brows
    for module in (blush_area, guide_area_builder, output_area):
        if hasattr(module, "paired_blush"):
            module.paired_blush = cheeks
    for module in (eyeshadow_area, guide_area_builder, output_area):
        if hasattr(module, "paired_eyeshadow"):
            module.paired_eyeshadow = shadows
    for module in (eyeliner_area, guide_area_builder, output_area):
        if hasattr(module, "paired_eyeliner"):
            module.paired_eyeliner = liners
    guide_area_builder.pair_sub_step = output_area.pair_sub_step = pair_each
    guide_area_builder.eyeliner_sub_step = line_each
    rules = output_area.PAIR_RULES
    if "blush" in rules:
        rules["blush"] = (cheeks, *rules["blush"][1:])


def has_cells(masks, side: str) -> bool:
    """짝 결과에 그 쪽 표가 있고 칠한 칸이 있는지. 한쪽만 재는 지표 도구는 그 쪽만 넘긴다."""
    mask = masks.get(side)
    return mask is not None and bool(mask.any())


def unknown_union(unknown) -> np.ndarray | None:
    """아이라인 모름 칸은 자리별 dict일 수 있어 한 표로 합친다."""
    if unknown is None or isinstance(unknown, np.ndarray):
        return unknown
    values = [value for value in unknown.values() if value is not None]
    return np.logical_or.reduce(values) if values else None


def install_from_env() -> Callable[[], None] | None:
    """A306_METHOD·A306_MODEL 환경 변수가 있으면 install을 부른다(sitecustomize용)."""
    method, model = os.environ.get("A306_METHOD"), os.environ.get("A306_MODEL")
    if method and model:
        store = os.environ.get("A306_STORE")
        install(
            method,
            Path(model),
            int(os.environ.get("A306_ORT_THREADS", "1")),
            Path(store) if store else None,
        )
        if os.environ.get("A306_PAIRING") == "each":
            install_each_side()
    return None
