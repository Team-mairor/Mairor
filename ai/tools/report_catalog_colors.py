"""색 추출 기준 세트 리포트와 수집 실행 요약을 만든다. 네트워크와 모델을 쓰지 않는다.

uv run python tools/report_catalog_colors.py reference
uv run python tools/report_catalog_colors.py reference --manifest ref/manifest.json --out r.md
uv run python tools/report_catalog_colors.py run /data/catalog-runs/20261105-103000-romand.jsonl
"""

import argparse
import sys
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR))

from app.tasks.catalog.report.reference import (  # noqa: E402
    build_report,
    load_manifest,
    render_markdown,
    synthetic_cases,
)
from app.tasks.catalog.report.runs import render_run_markdown, summarize_run  # noqa: E402
from app.tasks.catalog.runfile import RunFileError  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="화장품 색 추출 리포트")
    commands = parser.add_subparsers(dest="command", required=True)
    reference = commands.add_parser("reference", help="기준 세트로 색 추출 정확도를 잰다")
    reference.add_argument("--manifest", type=Path, help="실사 기준 세트(없으면 합성 세트만)")
    reference.add_argument("--no-synthetic", action="store_true", help="합성 세트를 빼고 실사만")
    reference.add_argument("--out", type=Path, help="마크다운을 쓸 파일(없으면 화면)")
    run = commands.add_parser("run", help="수집 실행 결과 파일을 요약한다")
    run.add_argument("file", type=Path)
    run.add_argument("--out", type=Path)
    return parser


def emit(text: str, out: Path | None) -> None:
    if out is None:
        sys.stdout.write(text)
    else:
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"썼다: {out}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "reference":
            cases = [] if args.no_synthetic else synthetic_cases()
            if args.manifest:
                cases += load_manifest(args.manifest)
            if not cases:
                print("사례가 없다", file=sys.stderr)
                return EXIT_USAGE
            emit(render_markdown(build_report(cases)), args.out)
        else:
            emit(render_run_markdown(summarize_run(args.file)), args.out)
    except (OSError, ValueError, KeyError, RunFileError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
