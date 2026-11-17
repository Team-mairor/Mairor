"""가림 찾기 모델(app/weights/occlusion_bisenet.v1.onnx)을 작은 입력으로도 돌게 바꿔 저장한다.

사용자 캠 게이지는 사진을 서버로 보내지 않아 브라우저가 이 모델을 돌린다.
서버는 숫자를 8비트로 줄인 판(occlusion_finder.MODEL_PATH)을 쓰지만, 이 도구는 줄이기 전
모델(SOURCE_PATH)에서 만든다. 8비트 판은 줄이면서 Resize 목표 크기가 상수 하나로 접혀
아래 2번 고치기가 바꿀 자리가 없고, 브라우저 정확도 · 시간도 줄이기 전 모델로 쟀다.

실행 (ai/ 폴더에서):
  uv run --group train python tools/gauge/export_occlusion_web.py <저장할 onnx> [--fp16]
--fp16이면 모델 안 숫자를 16비트 실수로 줄인다(입력 · 출력은 32비트 그대로).
FE가 쓰는 shared/occlusion의 파일은 --fp16으로 만든 것이다(shared/occlusion/README.md).

원래 모델은 입력 512 × 512에 맞춰 숫자가 박힌 곳이 두 종류 있다.
학습한 값은 그대로 두고 그 둘만 바꾼다.
1. 전체 평균 AveragePool(커널 = 특징 지도 크기, 출력 1 × 1) 4개 → GlobalAveragePool.
2. Resize가 키울 목표 크기 상수([16, 16] · [32, 32] · [64, 64] · [512, 512]) 4개
   → 입력 높이 · 너비 ÷ 32 · 16 · 8 · 1.
그래서 입력은 32의 배수여야 한다. 512에서는 원래 모델과 같은 답이다
(tests/test_gauge_occlusion_web.py). 크기별 정확도 · 시간은
docs/experiments/GAUGE_UNMEASURABLE_SMOOTHING.md에 있다.
"""

import argparse
import hashlib
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import numpy as np
import onnx
from onnx import helper, numpy_helper

from app.core.paths import WEIGHTS_DIR
from app.tasks.area.landmarks.occlusion_finder import INPUT_SIZE

SOURCE_PATH = WEIGHTS_DIR / "occlusion_bisenet.v1.onnx"
SOURCE_SHA256 = "14ccbd897384b1f3ebd92365bcdc0b7f593df74adc6ec3d9dc610c428259280c"
STRIDE_NAMES = ("flex_hw_start", "flex_hw_end", "flex_hw_axis")


def flexible(model: onnx.ModelProto) -> onnx.ModelProto:
    """model을 고쳐 입력 높이 · 너비가 정해지지 않은 모델로 돌려준다(model 자체를 바꾼다)."""
    graph = model.graph
    _global_pools(graph)
    _resize_targets(graph)
    _drop_unused_constants(graph)
    _sort(graph)
    for value in (graph.input[0], *graph.output):
        dims = value.type.tensor_type.shape.dim
        for axis, name in ((2, "height"), (3, "width")):
            dims[axis].ClearField("dim_value")
            dims[axis].dim_param = name
    del graph.value_info[:]
    onnx.checker.check_model(model)
    return model


def _global_pools(graph: onnx.GraphProto) -> None:
    for index, node in enumerate(list(graph.node)):
        if node.op_type != "AveragePool":
            continue
        attrs = {a.name: helper.get_attribute_value(a) for a in node.attribute}
        if list(attrs["kernel_shape"]) != list(attrs["strides"]) or any(attrs.get("pads", [0])):
            raise ValueError(f"전체 평균이 아닌 AveragePool: {node.name}")
        graph.node.remove(node)
        graph.node.insert(
            index,
            helper.make_node(
                "GlobalAveragePool", list(node.input), list(node.output), name=node.name
            ),
        )


def _resize_targets(graph: onnx.GraphProto) -> None:
    producer = {out: node for node in graph.node for out in node.output}
    graph.initializer.extend(
        numpy_helper.from_array(np.array([value], dtype=np.int64), name)
        for value, name in zip((2, 4, 0), STRIDE_NAMES, strict=True)
    )
    input_name = graph.input[0].name
    for node in list(graph.node):
        if node.op_type != "Resize":
            continue
        concat = producer[node.input[3]]
        size = numpy_helper.to_array(producer[concat.input[1]].attribute[0].t).tolist()
        if size[0] != size[1] or INPUT_SIZE % size[0]:
            raise ValueError(
                f"정사각형이 아니거나 {INPUT_SIZE}을 나누지 않는 목표 크기: {node.name}"
            )
        stride = INPUT_SIZE // size[0]
        shape, height_width = f"{node.name}_input_shape", f"{node.name}_input_hw"
        divisor, target = f"{node.name}_stride", f"{node.name}_target_hw"
        graph.initializer.append(
            numpy_helper.from_array(np.array([stride, stride], dtype=np.int64), divisor)
        )
        graph.node.extend(
            [
                helper.make_node("Shape", [input_name], [shape], name=shape),
                helper.make_node(
                    "Slice", [shape, *STRIDE_NAMES], [height_width], name=height_width
                ),
                helper.make_node("Div", [height_width, divisor], [target], name=target),
            ]
        )
        concat.input[1] = target


def _drop_unused_constants(graph: onnx.GraphProto) -> None:
    used = {name for node in graph.node for name in node.input}
    for node in list(graph.node):
        if node.op_type == "Constant" and not used & set(node.output):
            graph.node.remove(node)


def _sort(graph: onnx.GraphProto) -> None:
    known = {x.name for x in graph.input} | {x.name for x in graph.initializer} | {""}
    ordered, pending = [], list(graph.node)
    while pending:
        ready = [node for node in pending if all(name in known for name in node.input)]
        if not ready:
            raise ValueError("노드 순서를 정할 수 없다")
        for node in ready:
            ordered.append(node)
            known.update(node.output)
            pending.remove(node)
    del graph.node[:]
    graph.node.extend(ordered)


def half(model: onnx.ModelProto) -> onnx.ModelProto:
    """model 안 실수 숫자를 16비트로 줄인 모델. 입력 · 출력은 32비트 실수 그대로 둔다.

    브라우저가 처음 받는 파일이 절반이 되고 WebGPU에서 빨라진다. 판정 차이는
    docs/experiments/DEMO_AI_CHECK.md에 있다.
    """
    from onnxruntime.transformers.float16 import convert_float_to_float16

    return convert_float_to_float16(model, keep_io_types=True)


def source_problem() -> str | None:
    """줄이기 전 모델 파일을 쓸 수 없으면 그 까닭을, 쓸 수 있으면 None을 돌려준다.

    Git LFS 포인터만 받은 자리면 파일은 있어도 지문이 SOURCE_SHA256(app/weights/README.md)과 다르다.
    """
    if not SOURCE_PATH.is_file():
        return f"파일이 없다: {SOURCE_PATH}"
    digest = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        return f"지문이 다르다: {SOURCE_PATH} ({digest})"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", type=Path, help="저장할 onnx")
    parser.add_argument("--fp16", action="store_true", help="모델 안 숫자를 16비트 실수로 줄인다")
    args = parser.parse_args()
    problem = source_problem()
    if problem:
        raise SystemExit(f"줄이기 전 가림 찾기 모델을 쓸 수 없다: {problem}")
    model = flexible(onnx.load(str(SOURCE_PATH)))
    if args.fp16:
        model = half(model)
    args.target.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(args.target))
    print(args.target)


if __name__ == "__main__":
    main()
