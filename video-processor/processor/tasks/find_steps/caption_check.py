"""화면의 제품 글자(브랜드·제품명·색 번호)를 1080p 원본에서 다시 읽어 제품명을 바로잡는다.

영상 단계 추출은 빠르게 하려고 낮은 해상도로 보므로 작은 글자(색 번호)를 잘못 읽는다
(정답표: hince 22 얼루어 로즈를 '07 에크루'로 읽어 한 단계가 둘로 나뉨).
1. 위치 찾기: 낮은 해상도 영상을 받자마자 고르게 뽑은 사진 몇 장에서 제품 글자 상자를 찾는다(단계 뽑기와 동시).
   상자들을 합친 범위를 아래로 상자 높이만큼 더 넓혀 쓴다(모델이 브랜드·제품명 줄까지만 잡아 색 번호 줄이
   잘린 적이 있다). 합친 범위가 화면 절반을 넘으면(자리가 들쭉날쭉) 화면 전체를 쓴다.
   제품 글자가 없는 영상이면 다시 읽기를 건너뛴다.
2. 다시 읽기: 바르는 단계마다 가운데 시각의 1080p 사진을 그 범위로 잘라 한 번에 읽는다. 브랜드·제품명·호수를
   따로 받는다(find_steps/product.py).
3. 바꾸기: 읽은 글자가 받은 이름과 같은 제품으로 보일 때만(단어가 하나 이상 겹치거나 글자가 절반 이상 같음) 바꾼다.
   채널 로고 같은 다른 글자를 읽어도 이름이 바뀌지 않게 한다. 받은 이름에 있던 숫자(색 번호)가 읽은 글자에 하나도
   없으면 바꾸지 않는다. 잘려 읽힌 글자로 색이 다른 제품들이 같은 이름이 되어 한 단계로 합쳐지는 것을 막는다.
   읽은 글자가 받은 이름의 앞부분뿐이어도 바꾸지 않는다. 상자가 오른쪽 글자를 자르면 "Triple Pot Concealer"를
   "Triple Pot Conc", "01 라이트 브라운"을 "01 라이"로 읽는다(tiAQfOhz_GQ). 받은 이름의 가격 숫자가 그동안 이를
   우연히 막고 있었는데, 가격을 지우면서 잘린 글자가 이름을 덮게 되었다.
"""

import base64
import io
import json
import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

from processor.clients.gms import DEFAULT_MODEL, RateLimitBudgetExceeded, generate_content, response_json
from processor.core.paths import PROMPTS_DIR
from processor.schemas.gms_answers import PRODUCT, id_items
from processor.tasks.find_steps.product import label, split_product
from processor.tasks.find_steps.step_rules import drop_tool_names, merge_same_product

LOCATE_FRAMES = 8
MARGIN = 0.03
MAX_AREA = 0.5
FULL_FRAME = (0.0, 0.0, 1.0, 1.0)
ANSWER_ATTEMPTS = 2

logger = logging.getLogger("VideoProcessor")

LOCATE_PROMPT = (PROMPTS_DIR / "caption_locate.txt").read_text(encoding="utf-8")

READ_PROMPT = (PROMPTS_DIR / "caption_read.txt").read_text(encoding="utf-8")


def _ask(parts, schema, ids, *, phase, api_key, model, recorder) -> dict:
    """모든 imageId가 한 번씩 있는 답을 {imageId: 행}으로 돌려준다. 끝내 못 받으면 빈 결과다."""
    try:
        for attempt in range(ANSWER_ATTEMPTS):
            raw = generate_content(parts, schema, model=model, api_key=api_key, phase=phase,
                                   call_id=phase if attempt == 0 else f"{phase}-retry",
                                   recorder=recorder, timeout=120)
            try:
                rows = response_json(raw)["items"]
            except (ValueError, KeyError, IndexError):
                continue
            if sorted(r["imageId"] for r in rows) == sorted(ids):
                return {r["imageId"]: r for r in rows}
    except (RateLimitBudgetExceeded, OSError, ValueError) as error:
        logger.warning("[Caption check] %s GMS 실패: %s", phase, type(error).__name__)
    return {}


def grab(video: Path, second: float, width: int | None = None) -> bytes:
    scale = ["-vf", f"scale={width}:-2"] if width else []
    return subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-threads", "1",
         "-ss", f"{second:.3f}", "-i", str(video), "-frames:v", "1", *scale,
         "-c:v", "mjpeg", "-q:v", "2", "-f", "image2pipe", "pipe:1"],
        capture_output=True, check=True, timeout=60,
    ).stdout


def caption_box(boxes: list[list[int]]) -> tuple[float, float, float, float] | None:
    """사진마다 찾은 상자(0~1000)를 합쳐 (왼, 위, 오른, 아래) 비율로. 없으면 None, 너무 넓으면 화면 전체."""
    boxes = [b for b in boxes if b and len(b) == 4 and b[0] < b[2] and b[1] < b[3]]
    if not boxes:
        return None
    top, left = min(b[0] for b in boxes) / 1000, min(b[1] for b in boxes) / 1000
    bottom, right = max(b[2] for b in boxes) / 1000, max(b[3] for b in boxes) / 1000
    bottom = min(1.0, bottom + (bottom - top))
    box = (max(0.0, left - MARGIN), max(0.0, top - MARGIN), min(1.0, right + MARGIN), min(1.0, bottom + MARGIN))
    if (box[2] - box[0]) * (box[3] - box[1]) > MAX_AREA:
        return FULL_FRAME
    return tuple(round(v, 3) for v in box)


def locate_caption(video: Path, duration: float, *, api_key, model=DEFAULT_MODEL, recorder=None,
                   output_dir) -> tuple[float, float, float, float] | None:
    """영상 전체에 고르게 뽑은 사진에서 제품 글자 자리를 찾는다. 실패하면 None(다시 읽기를 건너뜀)."""
    times = [duration * (k + 1) / (LOCATE_FRAMES + 1) for k in range(LOCATE_FRAMES)]
    try:
        with ThreadPoolExecutor(max_workers=LOCATE_FRAMES) as pool:
            images = list(pool.map(lambda t: grab(video, t, 640), times))
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("[Caption check] 위치 찾기 사진을 못 뽑음: %s", type(error).__name__)
        return None
    ids = [f"f{k}" for k in range(len(times))]
    parts = [{"text": LOCATE_PROMPT}]
    for image_id, image in zip(ids, images):
        parts += [{"text": f"imageId={image_id}"},
                  {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(image).decode()}}]
    box_value = {"type": "ARRAY", "items": {"type": "INTEGER"}, "nullable": True}
    rows = _ask(parts, id_items("box", box_value, ids), ids, phase="caption_locate",
                api_key=api_key, model=model, recorder=recorder)
    box = caption_box([r.get("box") for r in rows.values()])
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "caption_box.json").write_text(json.dumps(
        {"times": times, "boxes": {k: r.get("box") for k, r in rows.items()}, "box": box}, indent=2),
        encoding="utf-8")
    logger.info("[Caption check] 제품 글자 자리 %s", box)
    return box


def crop(jpeg: bytes, box) -> bytes:
    image = Image.open(io.BytesIO(jpeg)).convert("RGB")
    w, h = image.size
    out = io.BytesIO()
    image.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))).save(
        out, format="JPEG", quality=90)
    return out.getvalue()


def read_captions(steps: list[dict], video: Path, box, *, api_key, model=DEFAULT_MODEL, recorder=None,
                  output_dir) -> dict[int, dict]:
    """바르는 단계의 가운데 시각 글자를 읽어 {단계 순번: {brand, name, shade}}를 돌려준다. 자리를 모르거나 실패하면 빈 결과다."""
    wanted = [i for i, s in enumerate(steps) if s.get("isCosmeticApplication")]
    if not wanted or box is None:
        return {}
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            crops = list(pool.map(
                lambda i: crop(grab(video, (steps[i]["absStart"] + steps[i]["absEnd"]) / 2), box), wanted))
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("[Caption check] 다시 읽을 사진을 못 뽑음: %s", type(error).__name__)
        return {}
    ids = [f"c{i}" for i in wanted]
    parts = [{"text": READ_PROMPT}]
    for image_id, image in zip(ids, crops):
        parts += [{"text": f"imageId={image_id}"},
                  {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(image).decode()}}]
    rows = _ask(parts, id_items("product", PRODUCT, ids), ids, phase="caption_read",
                api_key=api_key, model=model, recorder=recorder)
    read = {int(k[1:]): split_product(r.get("product")) for k, r in rows.items()}
    captions = {i: product for i, product in read.items() if product}
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "captions.json").write_text(
        json.dumps({str(i): captions.get(i) for i in wanted}, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[Caption check] 단계 %d개 중 글자 읽음 %d개", len(wanted), len(captions))
    return captions


def _words(name: str) -> set[str]:
    return {w for w in re.split(r"[\W_]+", name.casefold()) if len(w) >= 2 and not w.isdigit()}


def _squeeze(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def cut_short(old: str | None, new: str | None) -> bool:
    """읽은 글자가 받은 글자의 앞부분뿐인가(상자가 오른쪽 글자를 잘랐다)."""
    return bool(old) and len(_squeeze(new or "")) < len(_squeeze(old)) and _squeeze(old).startswith(_squeeze(new or ""))


def looks_same(old: str | None, new: str) -> bool:
    """다시 읽은 글자가 받은 이름과 같은 제품을 가리키는가. 받은 이름이 없으면 그대로 쓴다."""
    if not old:
        return True
    if re.search(r"\d", old) and not re.search(r"\d", new):
        return False
    if cut_short(old, new):
        return False
    return bool(_words(old) & _words(new)) or SequenceMatcher(None, _squeeze(old), _squeeze(new)).ratio() >= 0.5


def apply_captions(checked, captions):
    """다시 읽은 제품 글자로 이름을 바로잡고(받은 이름과 같은 제품으로 보일 때만), 같은 제품이 된 이웃 단계를 묶는다.

    이름 없는 단계는 읽은 글자를 그대로 받으므로, 바르는 단계에 도구 이름이 다시 붙지 않게 묶기 전에 한 번 더 뗀다.

    checked는 앞뒤 빈 구간 확인을 마친 단계, captions는 같은 순서의 {단계 순번: {brand, name, shade}}다.
    한 줄 글자도 받는다. 비교와 묶기는 세 칸을 이은 이름으로 하고, 단계에는 세 칸을 함께 남긴다.
    """
    read = {i: split_product(c) for i, c in captions.items()}
    read = {i: product for i, product in read.items() if product}
    adopted = {i: p for i, p in read.items() if looks_same(checked[i].get("productName"), label(p))
               and not cut_short((checked[i].get("product") or {}).get("shade"), p["shade"])}
    renames = {checked[i]["productName"]: p for i, p in adopted.items() if checked[i].get("productName")}
    named = []
    for i, step in enumerate(checked):
        product = adopted.get(i) or renames.get(step.get("productName"))
        if product and product != step.get("product"):
            step = step | {"product": product, "productName": label(product)}
            if label(product) != checked[i].get("productName"):
                step["videoProductName"] = checked[i].get("productName")
        named.append(step)
    rejected = [{"name": checked[i].get("productName"), "caption": label(p)}
                for i, p in read.items() if i not in adopted]
    return merge_same_product(drop_tool_names(named)), {"captionsRead": len(captions), "rejectedCaptions": rejected}
