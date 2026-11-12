"""색 품질 기준값을 정하려고 사람이 색 칸을 눈으로 확인하는 표와, 그 판정으로 만드는 기준값 리포트.

표본은 실행 결과 파일에서 색(HEX)과 근거 사진(imageUrl·bbox)이 둘 다 있는 칸이다.
표는 칸 주변 사진(빨간 사각형이 칸), 칸만 잘라 키운 사진, 계산한 색을 나란히 보여 주고
맞음·틀림·모름을 고르게 한다. 판정은 브라우저에 저장되고 CSV로 내려받는다.

리포트는 BE 판정표(ColorApprovalPolicy)와 같은 구분으로 센다.
SWATCH_CHIP·PRODUCT_PHOTO·WEB_PHOTO마다, 연결 근거가 사진 연결(OPTION_IMAGE·SINGLE_SHADE_PRODUCT)인
칸과 사진 속 표기 연결(LABEL_IN_IMAGE)인 칸을 나눠, 임계값 후보마다 통과하는 칸의 정확도를 낸다.
"""

import base64
import csv
import html
import io
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from app.tasks.catalog.contract import BBox
from app.tasks.catalog.runfile import read_run_file

QUALITY_SOURCES = ("SWATCH_CHIP", "PRODUCT_PHOTO", "WEB_PHOTO")
PHOTO_LINKS = {
    "SWATCH_CHIP": ("OPTION_IMAGE", "SINGLE_SHADE_PRODUCT"),
    "PRODUCT_PHOTO": ("OPTION_IMAGE", "SINGLE_SHADE_PRODUCT"),
    "WEB_PHOTO": ("OPTION_IMAGE",),
}
IMAGE_CHANGED = "IMAGE_CHANGED"
FAILURE_TEXT = {
    IMAGE_CHANGED: "수집한 뒤 원본 사진이 바뀌었다. 예전 색을 새 사진으로 판정할 수 없어 뺀다"
}
LABEL_LINK = "LABEL_IN_IMAGE"
TARGET_PRECISION = 0.95
MIN_SAMPLES = 30
MAX_WRONG_SHOWN = 10
VERDICTS = ("OK", "WRONG", "SKIP")
CONTEXT_SCALE = 4.0
CONTEXT_MAX = 360
CELL_SIZE = 96


@dataclass(frozen=True)
class Sample:
    file: str
    item_key: str
    evidence_key: str
    brand: str
    product: str
    shade: str
    printed_name: str | None
    hex: str
    source: str
    link: str
    quality: float | None
    image_url: str
    image_kind: str | None
    image_hash: str | None
    bbox: BBox | None

    @property
    def key(self) -> str:
        return f"{self.file}|{self.evidence_key}"


@dataclass(frozen=True)
class Crops:
    context: bytes
    cell: bytes


def collect_samples(paths: Iterable[Path]) -> list[Sample]:
    """색과 근거 사진이 둘 다 있는 칸. 영역이 없으면 사진 전체가 근거다."""
    samples: list[Sample] = []
    for path in paths:
        _, items = read_run_file(path)
        for item in items:
            evidence = {record.evidence_key: record for record in item.evidence}
            product = item.collected
            for shade in product.shades:
                for color in shade.colors:
                    record = evidence.get(color.evidence_key)
                    if not color.hex or record is None or not record.image_url:
                        continue
                    samples.append(
                        Sample(
                            file=path.name,
                            item_key=item.item_key,
                            evidence_key=color.evidence_key,
                            brand=product.brand,
                            product=product.name,
                            shade=shade.name,
                            printed_name=color.name,
                            hex=color.hex,
                            source=str(color.color_source),
                            link=str(color.shade_link),
                            quality=color.color_quality,
                            image_url=record.image_url,
                            image_kind=str(record.image_kind) if record.image_kind else None,
                            image_hash=record.image_hash,
                            bbox=record.bbox,
                        )
                    )
    return samples


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def crop_sample(image: Image.Image, box: BBox | None) -> Crops:
    """칸 주변(빨간 사각형)과 칸만 자른 사진. 좌표는 원본 픽셀, 영역이 없으면 사진 전체."""
    rgb = image.convert("RGB")
    box = box or BBox(x=0, y=0, width=rgb.width, height=rgb.height)
    cx, cy = box.x + box.width / 2, box.y + box.height / 2
    half_w = max(box.width * CONTEXT_SCALE, 60) / 2
    half_h = max(box.height * CONTEXT_SCALE, 60) / 2
    left, top = max(0, int(cx - half_w)), max(0, int(cy - half_h))
    right, bottom = min(rgb.width, int(cx + half_w)), min(rgb.height, int(cy + half_h))
    context = rgb.crop((left, top, max(right, left + 1), max(bottom, top + 1)))
    draw = ImageDraw.Draw(context)
    width = max(2, round(context.width / 150))
    draw.rectangle(
        (box.x - left, box.y - top, box.x - left + box.width, box.y - top + box.height),
        outline=(255, 0, 40),
        width=width,
    )
    context.thumbnail((CONTEXT_MAX, CONTEXT_MAX))
    cell = rgb.crop(
        (
            max(0, int(box.x)),
            max(0, int(box.y)),
            min(rgb.width, max(int(box.x + box.width), int(box.x) + 1)),
            min(rgb.height, max(int(box.y + box.height), int(box.y) + 1)),
        )
    )
    cell = cell.resize((CELL_SIZE, CELL_SIZE), Image.Resampling.NEAREST)
    return Crops(context=_png(context), cell=_png(cell))


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _card(index: int, sample: Sample, crops: Crops | None, failure: str | None) -> str:
    e = html.escape
    quality = "-" if sample.quality is None else f"{sample.quality:.3f}"
    if crops is not None:
        pictures = (
            f'<img class="ctx" src="{_data_url(crops.context)}" alt="칸 주변">'
            f'<img class="cell" src="{_data_url(crops.cell)}" alt="칸">'
        )
    else:
        reason = FAILURE_TEXT.get(failure or "", f"사진을 받지 못했다: {failure or ''}")
        pictures = f'<div class="fail">{e(reason)} (판정 제외)</div>'
    printed = f" · 사진 속 표기 <b>{e(sample.printed_name)}</b>" if sample.printed_name else ""
    buttons = (
        "".join(
            f'<label><input type="radio" name="v{index}" value="{value}"> {label}</label>'
            for value, label in (("OK", "맞음"), ("WRONG", "틀림"), ("SKIP", "모름"))
        )
        if crops is not None
        else ""
    )
    return f"""
<section class="card" data-key="{e(sample.key)}" data-index="{index}">
  <div class="head"><b>{e(sample.brand)}</b> {e(sample.product)}
    · 호수 <b>{e(sample.shade)}</b>{printed}</div>
  <div class="row">{pictures}
    <div class="swatch" style="background:{e(sample.hex)}"></div>
    <div class="meta">{e(sample.hex)}<br>{e(sample.source)} · {e(sample.link)}<br>
      품질 {quality} · {e(sample.image_kind or "-")}<br>
      <a href="{e(sample.image_url)}" target="_blank" rel="noreferrer">원본 사진</a></div>
  </div>
  <div class="vote">{buttons}</div>
</section>"""


def render_sheet(
    samples: list[Sample], crops: Mapping[str, Crops], failures: Mapping[str, str]
) -> str:
    """눈 확인 표 HTML 한 장. crops·failures의 키는 Sample.key다. 판정은 CSV로 내려받는다.

    진행률과 CSV는 지금 판정할 수 있는 카드(사진을 자른 칸)만 센다. 예전에 판정했더라도
    이번에 사진이 바뀌었거나 받지 못한 칸은 브라우저에 남은 답이 있어도 내보내지 않는다.
    """
    cards = "".join(
        _card(i, s, crops.get(s.key), failures.get(s.key)) for i, s in enumerate(samples)
    )
    judgeable = [s.key for s in samples if s.key in crops]
    keys = json.dumps(judgeable, ensure_ascii=False).replace("<", r"\u003c")
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>색 칸 눈 확인</title>
<style>
body{{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}}
.top{{position:sticky;top:0;background:#fff;padding:8px;border-bottom:1px solid #ddd;z-index:1}}
.card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px;margin:10px 0}}
.card.done{{opacity:.55}}
.row{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:8px 0}}
.ctx{{max-width:360px;max-height:360px;border:1px solid #ccc}}
.cell,.swatch{{width:96px;height:96px;border:1px solid #999;image-rendering:pixelated}}
.meta{{font-size:13px;line-height:1.5}}
.vote label{{margin-right:16px;font-size:15px}}
.fail{{color:#b00}}
</style></head><body>
<div class="top">
  <b>맞음</b>: 빨간 사각형이 그 호수의 색 칸이고,
  오른쪽 두 칸(잘라 낸 칸·계산한 색)의 색이 비슷하다.
  <b>틀림</b>: 사각형이 다른 호수·배경·글자·그림자이거나, 계산한 색이 칸과 다르다.
  <b>모름</b>: 판단하기 어렵다.<br>
  <span id="progress"></span> <button id="export">CSV 내려받기</button>
</div>
{cards}
<script>
const KEYS = {keys};
const STORE = "catalog-color-review";
let saved = {{}};
try {{ saved = JSON.parse(localStorage.getItem(STORE) || "{{}}"); }} catch (e) {{ saved = {{}}; }}
function save() {{ try {{ localStorage.setItem(STORE, JSON.stringify(saved)); }} catch (e) {{}} }}
function refresh() {{
  let n = 0;
  document.querySelectorAll(".card").forEach(card => {{
    if (!card.querySelector("input")) return;
    const v = saved[card.dataset.key];
    card.classList.toggle("done", !!v);
    if (!v) return;
    n++;
    const r = card.querySelector(`input[value="${{v}}"]`);
    if (r) r.checked = true;
  }});
  document.getElementById("progress").textContent = `${{n}} / ${{KEYS.length}} 판정`;
}}
document.addEventListener("change", e => {{
  const card = e.target.closest(".card");
  if (!card) return;
  saved[card.dataset.key] = e.target.value; save(); refresh();
}});
document.getElementById("export").addEventListener("click", () => {{
  const rows = ["file,evidenceKey,verdict"];
  for (const key of KEYS) {{
    if (!saved[key]) continue;
    const cut = key.indexOf("|");
    const file = key.slice(0, cut), evidenceKey = key.slice(cut + 1);
    const quote = v => '"' + v.replaceAll('"', '""') + '"';
    rows.push([file, evidenceKey, saved[key]].map(quote).join(","));
  }}
  const blob = new Blob(["\\ufeff" + rows.join("\\n")], {{type: "text/csv"}});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "color-review.csv"; a.click();
}});
refresh();
</script></body></html>
"""


def read_verdicts(path: Path) -> dict[str, str]:
    """CSV(file, evidenceKey, verdict)를 {표본 키: 판정}으로. 모르는 판정은 버린다."""
    verdicts: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            verdict = (row.get("verdict") or "").strip().upper()
            if verdict in VERDICTS:
                verdicts[f"{row['file']}|{row['evidenceKey']}"] = verdict
    return verdicts


@dataclass(frozen=True)
class Cut:
    threshold: float
    passed: int
    correct: int

    @property
    def precision(self) -> float:
        return self.correct / self.passed if self.passed else 0.0


@dataclass(frozen=True)
class Group:
    source: str
    links: str
    judged: list[tuple[float, bool]]
    wrong: tuple[Sample, ...] = ()

    @property
    def total(self) -> int:
        return len(self.judged)

    @property
    def correct(self) -> int:
        return sum(1 for _, ok in self.judged if ok)

    def cuts(self) -> list[Cut]:
        """판정한 칸의 품질값마다, 그 값 이상이 통과할 때의 정확도. 높은 값부터."""
        result: list[Cut] = []
        for threshold in sorted({quality for quality, _ in self.judged}, reverse=True):
            passed = [ok for quality, ok in self.judged if quality >= threshold]
            result.append(Cut(threshold, len(passed), sum(passed)))
        return result

    def recommend(self, target: float = TARGET_PRECISION) -> Cut | None:
        """통과하는 칸의 정확도가 target 이상인 가장 낮은 임계값. 없으면 None."""
        best = None
        for cut in self.cuts():
            if cut.precision >= target:
                best = cut
        return best


def build_groups(samples: list[Sample], verdicts: Mapping[str, str]) -> list[Group]:
    """출처 × (사진 연결 / 사진 속 표기 연결)별 판정. 모름과 품질 없는 칸은 뺀다.

    사진 연결은 BE 판정표처럼 출처마다 다르다. 웹 사진은 호수 전용 페이지(OPTION_IMAGE)만 인정한다.
    """
    groups: list[Group] = []
    for source in QUALITY_SOURCES:
        for name, links in (("사진 연결", PHOTO_LINKS[source]), ("사진 속 표기", (LABEL_LINK,))):
            members = [
                s
                for s in samples
                if s.source == source
                and s.link in links
                and s.quality is not None
                and verdicts.get(s.key) in ("OK", "WRONG")
            ]
            if members:
                judged = [(s.quality, verdicts[s.key] == "OK") for s in members]
                wrong = sorted(
                    (s for s in members if verdicts[s.key] == "WRONG"), key=lambda s: -s.quality
                )
                groups.append(Group(source, name, judged, tuple(wrong)))
    return groups


def _wrong_rows(wrong: Iterable[Sample], threshold: float | None) -> list[str]:
    rows = [
        "| 품질 | 후보 기준 통과 | 제품 | 호수 | 사진 속 표기 | 색 | 근거 |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in wrong:
        passes = "통과" if threshold is not None and s.quality >= threshold else "-"
        rows.append(
            f"| {s.quality:.3f} | {passes} | {s.brand} {s.product} | {s.shade}"
            f" | {s.printed_name or '-'} | {s.hex} | {s.evidence_key} |"
        )
    return rows


def render_report(samples: list[Sample], verdicts: Mapping[str, str]) -> str:
    """출처·연결 근거별 후보 기준, 통과한 칸과 그중 맞은 칸, 점수가 높은데 틀린 칸."""
    judged = [s for s in samples if s.key in verdicts]
    counts = Counter(verdicts[s.key] for s in judged)
    lines = [
        "# 색 품질 기준값 리포트",
        "",
        f"- 표본 {len(samples)}칸, 판정 {len(judged)}칸"
        f" (맞음 {counts['OK']}, 틀림 {counts['WRONG']}, 모름 {counts['SKIP']})",
        f"- 후보 기준: 통과하는 칸의 정확도가 {TARGET_PRECISION:.0%} 이상인 가장 낮은 임계값",
        f"- 판정 표본·통과 표본이 {MIN_SAMPLES}칸보다 적으면 부족이다."
        " 통과 표본이 부족하면 후보 정확도를 믿기 어려우니 칸을 더 모은다",
        "",
    ]
    groups = build_groups(samples, verdicts)
    if not groups:
        lines.append("판정한 칸이 없다.")
        return _joined(lines)
    lines += [
        "| 출처 | 연결 | 판정 | 맞음 | 전체 정확도 | 후보 기준 | 통과 | 통과 중 맞음"
        " | 통과 정확도 | 판정 표본 | 통과 표본 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for group in groups:
        best = group.recommend()
        rate = group.correct / group.total
        enough = _enough(group.total)
        passed_enough = _enough(best.passed if best else 0)
        if best is None:
            pick, passed, correct, precision = "없음", "0", "0", "-"
        else:
            pick, passed = f"{best.threshold:.3f}", str(best.passed)
            correct, precision = str(best.correct), f"{best.precision:.0%}"
        lines.append(
            f"| {group.source} | {group.links} | {group.total} | {group.correct} | {rate:.0%}"
            f" | {pick} | {passed} | {correct} | {precision} | {enough} | {passed_enough} |"
        )
    for group in groups:
        best = group.recommend()
        lines += ["", f"## {group.source} · {group.links}", ""]
        if best is None:
            lines += [
                f"정확도 {TARGET_PRECISION:.0%}를 넘는 구간이 없다(가장 높은 점수도 틀림).",
                "",
            ]
        lines += ["| 임계값 | 통과 | 맞음 | 정확도 |", "|---|---|---|---|"]
        for cut in group.cuts():
            lines.append(
                f"| {cut.threshold:.3f} | {cut.passed} | {cut.correct} | {cut.precision:.0%} |"
            )
        if group.wrong:
            lines += ["", "### 틀린 칸 (점수 높은 순)", ""]
            lines += _wrong_rows(group.wrong[:MAX_WRONG_SHOWN], best.threshold if best else None)
    return _joined(lines)


def _enough(count: int) -> str:
    return "충분" if count >= MIN_SAMPLES else f"부족({count}/{MIN_SAMPLES})"


def _joined(lines: list[str]) -> str:
    return "".join(line + "\n" for line in lines)
