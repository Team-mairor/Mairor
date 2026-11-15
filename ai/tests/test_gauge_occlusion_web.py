import numpy as np
import pytest

from app.tasks.area.landmarks.occlusion_finder import INPUT_NAME, MODEL_PATH

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
