import copy
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from app.clients.image_store import ImageFetchError, fetch_image
from app.core.errors import AppError
from app.schemas.guide import GuideInput
from app.services.guide_input import MAX_IMAGE_BYTES, load_step_images

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_input.json"
URL = "https://storage.example.com/s1-1.jpg"

VALID = {
    "videoId": "test_01",
    "durationSeconds": 60.0,
    "steps": [
        {
            "stepId": "s1",
            "order": 1,
            "startSeconds": 10.0,
            "endSeconds": 20.0,
            "makeup": "lip",
            "partLabel": "립",
            "summary": "틴트를 입술 안쪽부터 바른다.",
            "images": [{"url": URL, "at": 12.0}],
        }
    ],
}


def make_input(**step_overrides) -> dict:
    data = copy.deepcopy(VALID)
    data["steps"][0].update(step_overrides)
    return data


def error_text(e: pytest.ExceptionInfo[ValidationError]) -> str:
    return " / ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.value.errors())


def image_bytes(image_format: str = "JPEG", size: tuple[int, int] = (4, 2)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (255, 0, 0)).save(buffer, format=image_format)
    return buffer.getvalue()


def serve(files: dict[str, bytes]):
    """정해진 내용만 돌려주는 로컬 서버를 띄운다. 없는 경로는 404."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = files.get(self.path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(body or b"")

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_valid_input_and_gemini_sample_pass():
    GuideInput.model_validate(VALID)
    sample = GuideInput.model_validate_json(SAMPLE.read_text(encoding="utf-8"))

    assert len(sample.steps) == 19
    assert all(1 <= len(step.images) <= 3 for step in sample.steps)


def test_facts_and_product_are_optional():
    step = GuideInput.model_validate(VALID).steps[0]

    assert (step.facts, step.product) == (None, None)


@pytest.mark.parametrize("field", ["partLabel", "summary", "images"])
def test_missing_required_field_is_rejected(field):
    data = make_input()
    del data["steps"][0][field]

    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(data)

    assert f"steps.0.{field}" in error_text(e)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"endSeconds": 10.0}, "endSeconds는 startSeconds보다"),
        ({"images": [{"url": URL, "at": 25.0}]}, "images.0.at 25초가 단계 구간(10~20초) 밖"),
        ({"images": []}, "at least 1"),
        ({"images": [{"url": URL, "at": 12.0}] * 4}, "at most 3"),
        ({"images": [{"url": "file:///etc/passwd", "at": 12.0}]}, "URL scheme"),
    ],
    ids=["end-before-start", "image-out-of-step", "no-image", "too-many-images", "not-http"],
)
def test_step_range_and_images_are_checked(overrides, message):
    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(make_input(**overrides))

    assert message in error_text(e)


def test_step_past_video_end_is_rejected():
    """시각을 초로 달라고 했을 때처럼 분초 숫자(835 = 8분 35초)를 초로 받으면 여기서 걸린다."""
    data = make_input(startSeconds=50.0, endSeconds=835.0, images=[{"url": URL, "at": 51.0}])

    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(data)

    assert "s1의 endSeconds 835초가 영상 길이 60초보다 깁니다" in error_text(e)


@pytest.mark.parametrize(("field", "value"), [("stepId", "s1"), ("order", 1)])
def test_duplicate_step_is_rejected(field, value):
    data = make_input()
    second = copy.deepcopy(data["steps"][0]) | {"stepId": "s2", "order": 2, field: value}
    data["steps"].append(second)

    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(data)

    assert f"{field}가 겹칩니다" in error_text(e)


def test_images_are_loaded_with_type_and_size():
    guide_input = GuideInput.model_validate(VALID)

    images = load_step_images(guide_input, fetch=lambda url, limit: image_bytes("PNG", (8, 6)))

    image = images["s1"][0]
    assert (image.url, image.at, image.mime_type) == (URL, 12.0, "image/png")
    assert (image.width, image.height) == (8, 6)


def failing_fetch(url: str, limit: int) -> bytes:
    raise ImageFetchError("이미지를 받지 못했습니다 (HTTP 404)")


@pytest.mark.parametrize(
    ("fetch", "reason"),
    [
        (failing_fetch, "HTTP 404"),
        (lambda url, limit: b"not an image", "이미지로 열 수 없습니다"),
        (lambda url, limit: image_bytes("GIF"), "JPEG·PNG·WEBP만 받습니다 (GIF)"),
        (lambda url, limit: b"0" * limit, "5MB를 넘습니다"),
    ],
    ids=["not-found", "unreadable", "gif", "too-large"],
)
def test_unusable_image_is_rejected(fetch, reason):
    guide_input = GuideInput.model_validate(VALID)

    with pytest.raises(AppError) as e:
        load_step_images(guide_input, fetch=fetch)

    assert e.value.code == "STEP_IMAGE_UNUSABLE"
    assert e.value.details[0].field == "steps.0.images.0.url"
    assert reason in e.value.details[0].reason


def test_all_image_problems_are_reported_at_once():
    data = make_input(images=[{"url": URL, "at": 12.0}, {"url": URL, "at": 13.0}])

    with pytest.raises(AppError) as e:
        load_step_images(GuideInput.model_validate(data), fetch=failing_fetch)

    assert [d.field for d in e.value.details] == ["steps.0.images.0.url", "steps.0.images.1.url"]


def test_fetch_image_reads_up_to_limit_and_reports_http_errors():
    server = serve({"/big.jpg": b"0" * (MAX_IMAGE_BYTES + 10)})
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert len(fetch_image(f"{base}/big.jpg", MAX_IMAGE_BYTES + 1)) == MAX_IMAGE_BYTES + 1
        with pytest.raises(ImageFetchError, match="HTTP 404"):
            fetch_image(f"{base}/missing.jpg", 100)
    finally:
        server.shutdown()
