"""색 품질 기준값을 정하는 눈 확인 표와 리포트.

sheet: 실행 결과 파일의 색 칸마다 근거 사진을 받아(사이트 요청 규칙 그대로)
       칸 주변·칸·계산한 색을 나란히 둔 HTML 한 장을 만든다.
       브라우저에서 맞음·틀림·모름을 고르고 CSV를 내려받는다.
report: 그 CSV로 출처·연결 근거별 임계값 후보와 정확도 리포트(Markdown)를 만든다.
        네트워크를 쓰지 않는다.

    uv run python tools/review_catalog_colors.py sheet runs/*.jsonl --out review.html
    uv run python tools/review_catalog_colors.py report runs/*.jsonl --verdicts color-review.csv
"""

import argparse
import asyncio
import sys
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR))

from app.core.config import get_settings  # noqa: E402
from app.tasks.catalog.color.images import ImageUnusableError, load_image  # noqa: E402
from app.tasks.catalog.http import HttpConfig, HttpFailure, PoliteClient  # noqa: E402
from app.tasks.catalog.report.review import (  # noqa: E402
    IMAGE_CHANGED,
    Crops,
    Sample,
    collect_samples,
    crop_sample,
    read_verdicts,
    render_report,
    render_sheet,
)
from app.tasks.catalog.runfile import RunFileError  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="색 품질 기준값 눈 확인")
    commands = parser.add_subparsers(dest="command", required=True)
    sheet = commands.add_parser("sheet", help="눈 확인 표 HTML")
    sheet.add_argument("runs", type=Path, nargs="+", help="실행 결과 파일(.jsonl)")
    sheet.add_argument("--out", type=Path, required=True)
    report = commands.add_parser("report", help="판정 CSV로 기준값 리포트")
    report.add_argument("runs", type=Path, nargs="+")
    report.add_argument("--verdicts", type=Path, required=True, help="표에서 내려받은 CSV")
    report.add_argument("--out", type=Path, help="없으면 화면에 출력")
    return parser


async def fetch_crops(
    client: PoliteClient, samples: list[Sample]
) -> tuple[dict[str, Crops], dict[str, str]]:
    """사진을 한 번씩 받아 칸마다 자른다. 못 받았거나 수집 때와 다른 사진이면 실패로 남긴다."""
    crops: dict[str, Crops] = {}
    failures: dict[str, str] = {}
    by_url: dict[str, list[Sample]] = {}
    for sample in samples:
        by_url.setdefault(sample.image_url, []).append(sample)
    for index, (url, group) in enumerate(by_url.items(), start=1):
        print(f"[{index}/{len(by_url)}] {url}", file=sys.stderr)
        try:
            loaded = await load_image(client, url)
        except (ImageUnusableError, HttpFailure) as error:
            for sample in group:
                failures[sample.key] = getattr(error, "code", type(error).__name__)
            continue
        for sample in group:
            if sample.image_hash and sample.image_hash != loaded.sha256:
                failures[sample.key] = IMAGE_CHANGED
                continue
            crops[sample.key] = crop_sample(loaded.image, sample.bbox)
    return crops, failures


def main(argv: list[str] | None = None, *, client: PoliteClient | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        samples = collect_samples(args.runs)
    except (RunFileError, OSError) as error:
        print(f"실행 결과 파일을 읽지 못했다: {error}", file=sys.stderr)
        return EXIT_USAGE
    if args.command == "report":
        try:
            verdicts = read_verdicts(args.verdicts)
        except (OSError, KeyError) as error:
            print(f"판정 CSV를 읽지 못했다: {error}", file=sys.stderr)
            return EXIT_USAGE
        text = render_report(samples, verdicts)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        else:
            print(text)
        return EXIT_OK

    async def go() -> tuple[dict[str, Crops], dict[str, str]]:
        owned = client or PoliteClient(HttpConfig.from_settings(get_settings()))
        try:
            return await fetch_crops(owned, samples)
        finally:
            if client is None:
                await owned.aclose()

    crops, failures = asyncio.run(go())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_sheet(samples, crops, failures), encoding="utf-8")
    print(f"칸 {len(samples)}개, 사진 실패 {len(failures)}칸: {args.out}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
