"""실행 결과 파일(JSONL)을 요약한다. 공식 홈만으로 호수의 색이 얼마나 채워졌는지 보는 용도다.

호수 기준 채움률(color_status=EXTRACTED 비율)과 출처·연결 근거·품질 분포, 경고 코드 빈도를 센다.
공식 홈에서 못 채운 호수가 많을 때만 웹 사진 같은 보강 수단을 따로 검토한다.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.tasks.catalog.contract import ColorStatus
from app.tasks.catalog.runfile import read_run_file

QUALITY_BINS = ((0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01))


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
