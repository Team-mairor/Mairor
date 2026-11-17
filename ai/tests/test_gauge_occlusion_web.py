import hashlib
import re
from pathlib import Path

import numpy as np
import pytest

from app.tasks.area.landmarks.occlusion_finder import INPUT_NAME, MODEL_PATH, OCCLUDER

SHARED = Path(__file__).resolve().parents[2] / "shared" / "occlusion"
SHARED_MODEL = SHARED / "occlusion_bisenet.v1.web.fp16.onnx"

onnx = pytest.importorskip("onnx")
onnxruntime = pytest.importorskip("onnxruntime")


@pytest.fixture(scope="module")
def sessions():
    from tools.gauge.export_occlusion_web import SOURCE_PATH, flexible, source_problem

    problem = source_problem()
    if problem:
        pytest.skip(f"줄이기 전 가림 찾기 모델을 쓸 수 없다: {problem}")
    options = onnxruntime.SessionOptions()
    options.log_severity_level = 3
    original = onnxruntime.InferenceSession(
        str(SOURCE_PATH), options, providers=["CPUExecutionProvider"]
    )
    changed = flexible(onnx.load(str(SOURCE_PATH))).SerializeToString()
    flex = onnxruntime.InferenceSession(changed, options, providers=["CPUExecutionProvider"])
    return original, flex


def test_builds_from_the_model_before_quantizing():
    """서버는 8비트 판을 쓰지만 브라우저 모델은 줄이기 전 모델에서 만든다."""
    from tools.gauge.export_occlusion_web import SOURCE_PATH

    assert SOURCE_PATH.name == "occlusion_bisenet.v1.onnx"
    assert SOURCE_PATH.parent == MODEL_PATH.parent
    assert SOURCE_PATH != MODEL_PATH


def test_same_answer_as_the_original_model_at_512(sessions):
    """학습한 값은 그대로라 512에서는 줄이기 전 모델과 같은 가림 표가 나와야 한다."""
    original, flex = sessions
    x = np.random.default_rng(0).normal(size=(1, 3, 512, 512)).astype(np.float32)
    a = original.run(None, {INPUT_NAME: x})[0]
    b = flex.run(None, {INPUT_NAME: x})[0]

    assert np.abs(a - b).max() < 1e-4
    assert (a.argmax(1) == b.argmax(1)).all()


@pytest.mark.parametrize("size", [192, 256, 384])
def test_runs_at_smaller_inputs(sessions, size):
    _, flex = sessions
    x = np.zeros((1, 3, size, size), dtype=np.float32)
    out = flex.run(None, {INPUT_NAME: x})[0]

    assert out.shape == (1, 20, size, size)


def shared_fingerprint() -> tuple[str, int]:
    """shared/occlusion/README.md에 적힌 (SHA-256, 바이트 수)."""
    readme = (SHARED / "README.md").read_text(encoding="utf-8")
    found = re.search(r"SHA-256: `([0-9a-f]{64})` \(([\d,]+)B\)", readme)
    return found.group(1), int(found.group(2).replace(",", ""))


@pytest.fixture(scope="module")
def shared_model() -> bytes:
    data = SHARED_MODEL.read_bytes()
    if data.startswith(b"version https://git-lfs"):
        pytest.skip("FE용 가림 모델이 Git LFS 포인터만 있다")
    return data


def test_shared_model_matches_its_readme(shared_model):
    """FE가 받는 파일의 지문 · 크기가 README와 같아야 FE가 받은 파일을 확인할 수 있다."""
    digest, size = shared_fingerprint()

    assert hashlib.sha256(shared_model).hexdigest() == digest
    assert len(shared_model) == size


def test_shared_model_is_what_the_tool_makes_with_fp16(sessions, shared_model):
    """공유 파일은 export_occlusion_web.py --fp16 결과 그대로라 도구로 다시 만들 수 있다."""
    from tools.gauge.export_occlusion_web import SOURCE_PATH, flexible, half

    made = half(flexible(onnx.load(str(SOURCE_PATH)))).SerializeToString()

    assert hashlib.sha256(made).hexdigest() == hashlib.sha256(shared_model).hexdigest()


def test_shared_model_reads_384_like_the_32bit_model(sessions, shared_model):
    """FE가 쓰는 입력 384에서 이름 · 모양이 README와 같고, 32비트 판과 가림 판정이 거의 같다."""
    _, flex = sessions
    options = onnxruntime.SessionOptions()
    options.log_severity_level = 3
    half = onnxruntime.InferenceSession(shared_model, options, providers=["CPUExecutionProvider"])
    x = np.random.default_rng(0).normal(size=(1, 3, 384, 384)).astype(np.float32)

    out = half.run(None, {INPUT_NAME: x})[0]
    full = flex.run(None, {INPUT_NAME: x})[0]

    assert [i.name for i in half.get_inputs()] == [INPUT_NAME]
    assert [o.name for o in half.get_outputs()] == ["logits"]
    assert out.shape == (1, 20, 384, 384) and out.dtype == np.float32
    assert (out.argmax(1) == full.argmax(1)).mean() > 0.999
    assert ((out.argmax(1) == OCCLUDER) == (full.argmax(1) == OCCLUDER)).mean() > 0.999
