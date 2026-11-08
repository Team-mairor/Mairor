"""실행 결과 파일(JSONL)을 요약한다. 공식 홈만으로 호수의 색이 얼마나 채워졌는지 보는 용도다.

호수 기준 채움률(color_status=EXTRACTED 비율)과 출처·연결 근거·품질 분포, 경고 코드 빈도를 센다.
공식 홈에서 못 채운 호수가 많을 때만 웹 사진 같은 보강 수단을 따로 검토한다.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.tasks.catalog.contract import Color, ColorSource, ColorStatus, ShadeLink
from app.tasks.catalog.runfile import read_run_file

QUALITY_BINS = ((0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01))
BRAND_PASS_RATE = 0.7
USABLE_LINKS = frozenset(
    {ShadeLink.OPTION_IMAGE, ShadeLink.SINGLE_SHADE_PRODUCT, ShadeLink.LABEL_IN_IMAGE}
)


@dataclass
class RunSummary:
    run_id: str = ""
    products: int = 0
    products_without_shades: int = 0
    shades: int = 0
    shade_status: Counter[str] = field(default_factory=Counter)
    slots_with_color: int = 0
    by_source: Counter[str] = field(default_factory=Counter)
    by_link: Counter[str] = field(default_factory=Counter)
    quality_bins: Counter[str] = field(default_factory=Counter)
    warnings: Counter[str] = field(default_factory=Counter)

    @property
    def fill_rate(self) -> float | None:
        if not self.shades:
            return None
        return self.shade_status[ColorStatus.EXTRACTED.value] / self.shades


def _bin_label(quality: float) -> str:
    for low, high in QUALITY_BINS:
        if low <= quality < high:
            return f"{low:g}~{min(high, 1.0):g}"
    return "?"


def summarize_run(path: Path) -> RunSummary:
    header, items = read_run_file(path)
    summary = RunSummary(run_id=header.run_id)
    for item in items:
        product = item.collected
        summary.products += 1
        if not product.shades:
            summary.products_without_shades += 1
        for warning in product.warnings:
            summary.warnings[warning.split(":", 1)[0]] += 1
        for shade in product.shades:
            summary.shades += 1
            summary.shade_status[shade.color_status.value] += 1
            for color in shade.colors:
                if not color.has_color:
                    continue
                summary.slots_with_color += 1
                summary.by_source[color.color_source.value] += 1
                summary.by_link[color.shade_link.value] += 1
                if color.color_quality is not None:
                    summary.quality_bins[_bin_label(color.color_quality)] += 1
    return summary


def render_run_markdown(summary: RunSummary, title: str = "수집 실행 요약") -> str:
    rate = "-" if summary.fill_rate is None else f"{summary.fill_rate:.1%}"
    lines = [
        f"# {title}",
        "",
        f"- 실행 {summary.run_id}",
        f"- 상품 {summary.products}건(호수를 못 찾은 상품 {summary.products_without_shades}건)",
        f"- 호수 {summary.shades}개, 색을 구한 호수 비율 {rate}",
        f"- 색이 있는 칸 {summary.slots_with_color}개",
        "",
    ]
    for heading, counter in (
        ("호수 상태", summary.shade_status),
        ("색 출처", summary.by_source),
        ("연결 근거", summary.by_link),
        ("품질 분포", summary.quality_bins),
        ("경고 코드", summary.warnings),
    ):
        lines += [f"## {heading}", ""]
        if not counter:
            lines += ["(없음)", ""]
            continue
        lines += ["| 값 | 건수 |", "| --- | --- |"]
        lines += [f"| {key} | {count} |" for key, count in sorted(counter.items())]
        lines.append("")
    return "\n".join(lines)


@dataclass
class BrandSummary:
    """브랜드 하나의 채움률. 호수는 서비스에서 쓸 수 있는 색 칸이 하나라도 있으면 채운 것이다."""

    brand: str
    products: int = 0
    shades: int = 0
    usable_shades: int = 0
    by_link: Counter[str] = field(default_factory=Counter)
    warnings: Counter[str] = field(default_factory=Counter)

    @property
    def usable_rate(self) -> float | None:
        return self.usable_shades / self.shades if self.shades else None

    @property
    def passed(self) -> bool:
        rate = self.usable_rate
        return rate is not None and rate >= BRAND_PASS_RATE


def is_usable_color(color: Color, min_quality: float) -> bool:
    """백엔드가 쓸 수 있는 색인가. 연결 근거가 분명하고 사진 색은 품질이 임계값 이상이어야 한다.

    모델 추정 색은 쓰지 않는다. 임계값은 백엔드가 정하며 여기서는 리포트용 가정이다.
    """
    if not color.has_color or color.shade_link not in USABLE_LINKS:
        return False
    if color.color_source is ColorSource.LLM_ESTIMATE:
        return False
    return color.color_quality is None or color.color_quality >= min_quality


def summarize_brands(paths: list[Path], min_quality: float) -> list[BrandSummary]:
    """실행 결과 파일 여러 개를 브랜드별로 묶어 채움률을 센다. 브랜드 이름 순이다."""
    brands: dict[str, BrandSummary] = {}
    for path in paths:
        _, items = read_run_file(path)
        for item in items:
            product = item.collected
            summary = brands.setdefault(product.brand, BrandSummary(product.brand))
            summary.products += 1
            for warning in product.warnings:
                summary.warnings[warning.split(":", 1)[0]] += 1
            for shade in product.shades:
                summary.shades += 1
                usable = [c for c in shade.colors if is_usable_color(c, min_quality)]
                if usable:
                    summary.usable_shades += 1
                    summary.by_link[usable[0].shade_link.value] += 1
    return sorted(brands.values(), key=lambda b: b.brand)


def render_brands_markdown(brands: list[BrandSummary], min_quality: float) -> str:
    """브랜드별 채움률 표. 호수의 70% 이상이 쓸 수 있는 색이면 "된 브랜드"다."""
    passed = sum(1 for brand in brands if brand.passed)
    lines = [
        "# 브랜드별 색 채움률",
        "",
        f"- 쓸 수 있는 색: 연결 근거가 분명하고(OPTION_IMAGE·SINGLE_SHADE_PRODUCT·LABEL_IN_IMAGE) "
        f"사진 색은 품질 {min_quality:g} 이상",
        f"- 된 브랜드: 호수의 {BRAND_PASS_RATE:.0%} 이상이 쓸 수 있는 색인 브랜드 "
        f"({passed}/{len(brands)})",
        "",
        "| 브랜드 | 상품 | 호수 | 쓸 수 있는 호수 | 비율 | 판정 | 연결 근거 | 많은 경고 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for brand in brands:
        rate = "-" if brand.usable_rate is None else f"{brand.usable_rate:.0%}"
        links = ", ".join(f"{k} {v}" for k, v in sorted(brand.by_link.items())) or "-"
        warnings = ", ".join(f"{k} {v}" for k, v in brand.warnings.most_common(3)) or "-"
        verdict = "된다" if brand.passed else "안 된다"
        lines.append(
            f"| {brand.brand} | {brand.products} | {brand.shades} | {brand.usable_shades} "
            f"| {rate} | {verdict} | {links} | {warnings} |"
        )
    lines.append("")
    return "\n".join(lines)
