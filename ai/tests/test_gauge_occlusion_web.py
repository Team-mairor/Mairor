import numpy as np
import pytest

from app.tasks.area.landmarks.occlusion_finder import INPUT_NAME, MODEL_PATH, check_model_file

onnx = pytest.importorskip("onnx")
onnxruntime = pytest.importorskip("onnxruntime")


@pytest.fixture(scope="module")
def sessions():
    from tools.gauge.export_occlusion_web import flexible

    try:
        check_model_file(MODEL_PATH)
    except Exception as error:
        pytest.skip(f"가림 찾기 모델 파일이 없다: {error}")
    options = onnxruntime.SessionOptions()
    options.log_severity_level = 3
    original = onnxruntime.InferenceSession(
        str(MODEL_PATH), options, providers=["CPUExecutionProvider"]
    )
    changed = flexible(onnx.load(str(MODEL_PATH))).SerializeToString()
    flex = onnxruntime.InferenceSession(changed, options, providers=["CPUExecutionProvider"])
    return original, flex


def test_same_answer_as_the_service_model_at_512(sessions):
    """학습한 값은 그대로라 512에서는 서비스 모델과 같은 가림 표가 나와야 한다."""
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
