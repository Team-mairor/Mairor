"""화장품 수집기 명령줄. 사이트 목록, 상품 주소·목록, 한 건 수집, 새 브랜드 홈, 목록 수집이다.

--colors는 호수 사진에서 색(HEX)을 계산하고, --vision은 모델이 사진 종류와 칸 위치를 찾게 하며,
--estimate는 색을 못 구한 호수의 이름 기반 추정 색(LLM_ESTIMATE, 기본 꺼짐)을 더한다.
운영 수집은 목록에서 켜진(enabled) 사이트에만 한다.
켜지지 않은 사이트는 구조를 확인하는 소량 요청에 한해 --allow-disabled 로만 접근한다.

    uv run python tools/collect_catalog.py sites
    uv run python tools/collect_catalog.py find --brand 롬앤 --name "쥬시 틴트" --allow-disabled
    uv run python tools/collect_catalog.py list --brand 롬앤 --out p.jsonl --allow-disabled
    uv run python tools/collect_catalog.py list --brand 롬앤 --out p.jsonl --resume
    uv run python tools/collect_catalog.py discover --brand 새브랜드 --alias NewBrand
    uv run python tools/collect_catalog.py collect --brand 롬앤 --products p.jsonl --name romand
    uv run python tools/collect_catalog.py product --brand 롬앤 --url https://... --render
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR))

from app.clients.llm import Llm, LlmError, get_catalog_llm  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.tasks.catalog.checkpoint import (  # noqa: E402
    Checkpoint,
    CheckpointError,
    checkpoint_path_for,
)
from app.tasks.catalog.discover.official import DiscoverStatus, discover_site  # noqa: E402
from app.tasks.catalog.discover.registry import (  # noqa: E402
    BrandSite,
    RegistryError,
    SiteRegistry,
    load_registry,
)
from app.tasks.catalog.extract.collect import collect_product  # noqa: E402
from app.tasks.catalog.extract.product import ExtractError  # noqa: E402
from app.tasks.catalog.find.category import crawl_categories  # noqa: E402
from app.tasks.catalog.find.finder import FindStatus, find_product, resolve_platform  # noqa: E402
from app.tasks.catalog.find.urls import Candidate, is_supported  # noqa: E402
from app.tasks.catalog.http import HttpConfig, HttpFailure, PoliteClient  # noqa: E402
from app.tasks.catalog.render.browser import PlaywrightRenderer, Renderer  # noqa: E402
from app.tasks.catalog.runfile import RunFileError, RunFileWriter  # noqa: E402
from app.tasks.catalog.runner import (  # noqa: E402
    collect_candidates,
    new_header,
    read_candidates,
)

EXIT_OK = 0
EXIT_NOT_FOUND = 1
EXIT_USAGE = 2
EXIT_STOPPED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="화장품 공식 홈 수집기")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("sites", help="사이트 목록과 상태")

    find = commands.add_parser("find", help="브랜드의 공식 홈에서 제품 상세 주소 찾기")
    find.add_argument("--brand", required=True)
    find.add_argument("--name", required=True, help="제품 이름")
    find.add_argument(
        "--allow-disabled", action="store_true", help="켜지지 않은 사이트도 소량 확인"
    )

    discover = commands.add_parser("discover", help="목록에 없는 브랜드의 공식 홈 찾기")
    discover.add_argument("--brand", required=True)
    discover.add_argument("--alias", action="append", default=[], help="다른 이름(여러 번)")
    discover.add_argument("--hint", help="모델에게 줄 참고 한 줄")

    product = commands.add_parser("product", help="상품 상세 주소 하나를 수집해 JSON으로 보기")
    product.add_argument("--brand", required=True)
    product.add_argument("--url", required=True, help="상품 상세 주소")
    product.add_argument(
        "--render", action="store_true", help="정적 HTML에 호수가 없으면 브라우저로 그려서 다시"
    )
    product.add_argument("--colors", action="store_true", help="호수 사진을 받아 색(HEX)도 계산")
    product.add_argument(
        "--vision",
        action="store_true",
        help="--colors와 함께: 모델이 사진 종류와 칸 위치를 찾게 한다(모델 호출 발생)",
    )
    product.add_argument(
        "--estimate",
        action="store_true",
        help="색을 못 구한 호수는 이름으로 모델이 추정(LLM_ESTIMATE, 백엔드가 켠 경우에만 쓰임)",
    )
    product.add_argument(
        "--allow-disabled", action="store_true", help="켜지지 않은 사이트도 소량 확인"
    )

    collect = commands.add_parser(
        "collect", help="상품 후보 목록(list 결과)을 수집해 실행 결과 파일로"
    )
    collect.add_argument("--brand", required=True)
    collect.add_argument("--products", type=Path, required=True, help="list 명령이 만든 JSONL")
    collect.add_argument("--name", help="실행 이름(파일 이름에 들어간다)")
    collect.add_argument("--out-dir", type=Path, help="기본은 설정의 실행 결과 폴더")
    collect.add_argument("--resume", type=Path, help="끊긴 실행 결과 파일을 이어서")
    collect.add_argument("--retry-failed", action="store_true")
    collect.add_argument("--limit", type=int, help="이번에 처리할 최대 상품 수")
    collect.add_argument("--render", action="store_true")
    collect.add_argument("--colors", action="store_true")
    collect.add_argument("--vision", action="store_true")
    collect.add_argument("--estimate", action="store_true")
    collect.add_argument("--allow-disabled", action="store_true")

    listing = commands.add_parser("list", help="브랜드의 카테고리를 돌며 상품 목록 모으기")
    listing.add_argument("--brand", required=True)
    listing.add_argument("--out", type=Path, required=True, help="상품 후보를 한 줄씩 쓸 파일")
    listing.add_argument("--resume", action="store_true", help="끝낸 카테고리는 건너뛰고 이어서")
    listing.add_argument("--retry-failed", action="store_true", help="실패한 카테고리만 다시")
    listing.add_argument(
        "--allow-disabled", action="store_true", help="켜지지 않은 사이트도 소량 확인"
    )
    listing.add_argument("--max-pages", type=int, default=100)
    return parser


def http_config(registry: SiteRegistry) -> HttpConfig:
    """요청 설정. robots 예외는 환경설정과 사이트 목록의 robots_exempt를 합친다."""
    config = HttpConfig.from_settings(get_settings())
    return replace(
        config, robots_exempt_hosts=config.robots_exempt_hosts | registry.robots_exempt_hosts()
    )


def _site_for(registry: SiteRegistry, brand: str, allow_disabled: bool) -> BrandSite | None:
    site = registry.find(brand)
    if site is None:
        print(f"목록에 없는 브랜드다: {brand}", file=sys.stderr)
        return None
    if site.domain is None:
        print(f"{site.brand}: 공식 홈이 없다", file=sys.stderr)
        return None
    if not site.can_collect and not allow_disabled:
        print(
            f"{site.brand}: 운영 수집이 켜지지 않았다"
            f"(policy={site.policy}, enabled={site.enabled}). 구조 확인만 할 때는 --allow-disabled",
            file=sys.stderr,
        )
        return None
    return site


def print_sites(registry: SiteRegistry) -> int:
    print("brand\tdomain\tplatform\ttechnical\tpolicy\tenabled")
    for site in registry.sites:
        print(
            f"{site.brand}\t{site.domain or '-'}\t{site.platform}\t{site.technical}"
            f"\t{site.policy}\t{'on' if site.enabled else 'off'}"
        )
    return EXIT_OK


async def run_find(client: PoliteClient, site: BrandSite, name: str) -> int:
    result = await find_product(client, site, name)
    print(f"platform={result.platform} status={result.status} tried={','.join(result.tried)}")
    if result.status is FindStatus.FOUND and result.candidate is not None:
        print(f"{result.candidate.product_id}\t{result.candidate.url}\t{result.candidate.title}")
        return EXIT_OK
    for alternative in result.alternatives:
        print(f"후보\t{alternative.product_id}\t{alternative.url}\t{alternative.title}")
    return EXIT_NOT_FOUND


async def run_discover(
    client: PoliteClient, llm: Llm, registry: SiteRegistry, args: argparse.Namespace
) -> int:
    known = registry.find(args.brand)
    if known is not None:
        print(f"이미 목록에 있다: {known.brand} {known.domain or '-'}")
        return EXIT_OK
    result = await discover_site(client, llm, args.brand, aliases=tuple(args.alias), hint=args.hint)
    print(f"status={result.status}")
    for host, reason in result.rejected:
        print("제외", host, reason, sep="\t")
    for accepted in result.accepted:
        print("후보", accepted.host, accepted.site.platform, accepted.reason, sep="\t")
    if result.status is not DiscoverStatus.FOUND or result.site is None:
        return EXIT_NOT_FOUND
    site = result.site
    lines = [
        "brand_sites.yaml에 더할 항목(정책 확인 전이라 꺼 둔다):",
        f"- brand: {site.brand}",
        f"  domain: {site.domain}",
        f"  language: {site.language}",
        f"  platform: {site.platform}",
        '  technical: "UNKNOWN"',
    ]
    print(*lines, sep=chr(10))
    return EXIT_OK


async def run_product(
    client: PoliteClient,
    site: BrandSite,
    url: str,
    renderer: Renderer | None,
    colors: bool = False,
    llm: Llm | None = None,
    estimate: bool = False,
) -> int:
    platform = await resolve_platform(client, site)
    try:
        product, raw = await collect_product(
            client,
            site,
            platform,
            url,
            item_key="000001",
            renderer=renderer,
            colors=colors,
            llm=llm,
            estimate=estimate,
        )
    except ExtractError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return EXIT_NOT_FOUND
    print(
        json.dumps(
            {"collected": product.to_wire(), "raw": raw}, ensure_ascii=False, indent=2, default=str
        )
    )
    return EXIT_OK


async def run_collect(
    client: PoliteClient,
    site: BrandSite,
    args: argparse.Namespace,
    renderer: Renderer | None,
    llm: Llm | None,
) -> int:
    platform = await resolve_platform(client, site)
    candidates = read_candidates(args.products)
    try:
        if args.resume:
            writer = RunFileWriter.resume(args.resume)
        else:
            directory = args.out_dir or get_settings().catalog_run_dir
            name = args.name or site.domain.replace(".", "-")
            writer = RunFileWriter.create(directory, new_header(site), name)
    except (RunFileError, OSError) as error:
        print(f"실행 결과 파일 오류: {error}", file=sys.stderr)
        return EXIT_USAGE
    with writer:
        checkpoint = Checkpoint.load_or_create(
            checkpoint_path_for(writer.path), writer.header.run_id
        )
        try:
            stats = await collect_candidates(
                client,
                site,
                platform,
                candidates,
                writer,
                checkpoint,
                renderer=renderer,
                colors=args.colors,
                llm=llm,
                estimate=args.estimate,
                retry_failed=args.retry_failed,
                limit=args.limit,
            )
        except HttpFailure as error:
            print(f"{error.code}: {error} (그때까지 {writer.path} 에 저장했다)", file=sys.stderr)
            return EXIT_STOPPED
    print(f"{stats.written}건을 썼다, 실패 {len(stats.failed)}건, 건너뜀 {stats.skipped}건")
    print(f"실행 결과 파일: {writer.path}")
    return EXIT_OK if not stats.failed else EXIT_NOT_FOUND


async def run_list(
    client: PoliteClient,
    site: BrandSite,
    out: Path,
    *,
    resume: bool,
    retry_failed: bool,
    max_pages: int,
) -> int:
    platform = await resolve_platform(client, site)
    if not is_supported(platform):
        print(f"{site.brand}: 상품 주소 규칙을 모르는 사이트 종류다({platform})", file=sys.stderr)
        return EXIT_NOT_FOUND
    checkpoint_path = out.with_name(out.name + ".checkpoint.json")
    if not resume and (out.exists() or checkpoint_path.exists()):
        print(f"이미 있다: {out}. 이어서 하려면 --resume", file=sys.stderr)
        return EXIT_USAGE
    checkpoint = Checkpoint.load_or_create(checkpoint_path, run_id=site.source)
    skip = checkpoint.done if retry_failed else checkpoint.done | frozenset(checkpoint.failed)
    written = 0

    async def on_done(category: str, candidates: list[Candidate]) -> None:
        nonlocal written
        with out.open("a", encoding="utf-8", newline="\n") as handle:
            for candidate in candidates:
                handle.write(json.dumps(asdict(candidate), ensure_ascii=False) + "\n")
                written += 1
        checkpoint.mark_done(category)

    async def on_failed(category: str, error: HttpFailure) -> None:
        checkpoint.mark_failed(category, error.code)

    try:
        await crawl_categories(
            client,
            site,
            platform,
            skip=skip,
            on_done=on_done,
            on_failed=on_failed,
            max_pages=max_pages,
        )
    except HttpFailure as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return EXIT_STOPPED
    failed = checkpoint.failed_keys()
    print(
        f"카테고리 {len(checkpoint.done)}개 완료, 실패 {len(failed)}개, "
        f"이번에 {written}건을 썼다: {out}"
    )
    return EXIT_OK if not failed else EXIT_NOT_FOUND


async def _run(
    args: argparse.Namespace,
    registry: SiteRegistry,
    client: PoliteClient,
    renderer: Renderer | None,
    llm: Llm | None,
) -> int:
    if args.command == "discover":
        try:
            return await run_discover(client, llm or get_catalog_llm(), registry, args)
        except HttpFailure as error:
            print(f"{error.code}: {error}", file=sys.stderr)
            return EXIT_STOPPED
        except LlmError as error:
            print(f"모델 호출 실패({error.kind}): {error}", file=sys.stderr)
            return EXIT_STOPPED
    site = _site_for(registry, args.brand, args.allow_disabled)
    if site is None:
        return EXIT_USAGE
    try:
        if args.command == "find":
            return await run_find(client, site, args.name)
        if args.command == "collect":
            needs_model = args.vision or args.estimate
            model = (llm or get_catalog_llm()) if needs_model else None
            return await run_collect(client, site, args, renderer, model)
        if args.command == "product":
            needs_model = args.vision or args.estimate
            model = (llm or get_catalog_llm()) if needs_model else None
            return await run_product(
                client, site, args.url, renderer, args.colors, model, args.estimate
            )
        return await run_list(
            client,
            site,
            args.out,
            resume=args.resume,
            retry_failed=args.retry_failed,
            max_pages=args.max_pages,
        )
    except HttpFailure as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return EXIT_STOPPED
    except CheckpointError as error:
        print(f"체크포인트 오류: {error}", file=sys.stderr)
        return EXIT_USAGE


def main(
    argv: list[str] | None = None,
    *,
    registry: SiteRegistry | None = None,
    client: PoliteClient | None = None,
    renderer: Renderer | None = None,
    llm: Llm | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        loaded = registry or load_registry()
    except RegistryError as error:
        print(f"사이트 목록 오류: {error}", file=sys.stderr)
        return EXIT_USAGE
    if args.command == "sites":
        return print_sites(loaded)

    async def go() -> int:
        owned = client or PoliteClient(http_config(loaded))
        browser = renderer
        if browser is None and getattr(args, "render", False):
            browser = PlaywrightRenderer(owned)
        try:
            return await _run(args, loaded, owned, browser, llm)
        finally:
            if browser is not None and renderer is None:
                await browser.close()
            if client is None:
                await owned.aclose()

    return asyncio.run(go())


if __name__ == "__main__":
    sys.exit(main())
