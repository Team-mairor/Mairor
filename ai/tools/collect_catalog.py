"""화장품 수집기 명령줄. 사이트 목록, 상품 주소·목록, 한 건 수집, 새 브랜드 홈, 목록 수집이다.

--colors는 호수 사진에서 색(HEX)을 계산하고, --vision은 모델이 사진 종류와 칸 위치를 찾게 하며,
--estimate는 색을 못 구한 호수의 이름 기반 추정 색(LLM_ESTIMATE, 기본 꺼짐)을 더한다.
--classify는 목록에 type_hint가 없는 상품의 종류를 모델이 고른다(종류가 없으면 적재되지 않는다).
운영 수집은 목록에서 켜진(enabled) 사이트에만 한다.
켜지지 않은 사이트는 구조를 확인하는 소량 요청에 한해 --allow-disabled 로만 접근한다.

    uv run python tools/collect_catalog.py sites
    uv run python tools/collect_catalog.py find --brand 롬앤 --name "쥬시 틴트" --allow-disabled
    uv run python tools/collect_catalog.py list --brand 롬앤 --out p.jsonl --allow-disabled
    uv run python tools/collect_catalog.py list --brand 롬앤 --out p.jsonl --resume
    uv run python tools/collect_catalog.py discover --brand 새브랜드 --alias NewBrand
    uv run python tools/collect_catalog.py collect --brand 롬앤 --products p.jsonl --name romand
    uv run python tools/collect_catalog.py product --brand 롬앤 --url https://... --render
    uv run python tools/collect_catalog.py upload catalog-runs/20261111-070448-romand.jsonl

CATALOG_RUNS_STORE=s3이면 collect가 끝난 뒤 결과 파일과 manifest를 S3에 올린다.
올리지 못해도 로컬 파일은 남고, upload로 다시 올린다.
올린 실행은 이어 쓰지 않는다. 실패한 상품은 --retry-of <처음 파일>로 새 실행을 만든다.
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
from app.clients.web_search import GeminiSearch, WebSearch  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.tasks.catalog.checkpoint import (  # noqa: E402
    Checkpoint,
    CheckpointError,
    checkpoint_path_for,
)
from app.tasks.catalog.discover.registry import (  # noqa: E402
    BrandSite,
    RegistryError,
    SiteRegistry,
    load_registry,
)
from app.tasks.catalog.discover.resolve import (  # noqa: E402
    discover_and_admit,
    resolve_site,
)
from app.tasks.catalog.discover.site_store import (  # noqa: E402
    SiteStore,
    StoreError,
    build_store,
)
from app.tasks.catalog.extract.collect import collect_product  # noqa: E402
from app.tasks.catalog.extract.product import ExtractError  # noqa: E402
from app.tasks.catalog.find.category import crawl_categories  # noqa: E402
from app.tasks.catalog.find.finder import FindStatus, find_product, resolve_platform  # noqa: E402
from app.tasks.catalog.find.urls import Candidate, is_supported  # noqa: E402
from app.tasks.catalog.http import HttpConfig, HttpFailure, PoliteClient  # noqa: E402
from app.tasks.catalog.render.browser import PlaywrightRenderer, Renderer  # noqa: E402
from app.tasks.catalog.runfile import RunFileError, RunFileWriter, read_run_file  # noqa: E402
from app.tasks.catalog.runner import (  # noqa: E402
    collect_candidates,
    new_header,
    read_candidates,
)
from app.tasks.catalog.upload import RunUploader, UploadError, build_uploader  # noqa: E402

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
        "--classify", action="store_true", help="모델이 상품 종류를 고른다(모델 호출 발생)"
    )
    product.add_argument(
        "--type", help="상품 종류 코드(예: LIP_TINT). 주면 모델 분류를 하지 않는다"
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
    collect.add_argument(
        "--resume", type=Path, help="끊긴 실행 결과 파일을 이어서(S3에 올리기 전까지만)"
    )
    collect.add_argument(
        "--retry-of",
        type=Path,
        help="그 실행에서 실패한 상품만 새 실행(새 파일·runId)으로 다시 수집",
    )
    collect.add_argument("--retry-failed", action="store_true")
    collect.add_argument("--limit", type=int, help="이번에 처리할 최대 상품 수")
    collect.add_argument("--render", action="store_true")
    collect.add_argument("--colors", action="store_true")
    collect.add_argument("--vision", action="store_true")
    collect.add_argument("--estimate", action="store_true")
    collect.add_argument(
        "--classify",
        action="store_true",
        help="목록에 type_hint가 없는 상품은 모델이 종류를 고른다(모델 호출 발생)",
    )
    collect.add_argument("--allow-disabled", action="store_true")

    upload = commands.add_parser("upload", help="실행 결과 파일을 S3에 다시 올리기")
    upload.add_argument("files", type=Path, nargs="+", help="실행 결과 파일(.jsonl)")

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


def _usable(site: BrandSite, allow_disabled: bool) -> BrandSite | None:
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


async def _resolve_site(
    registry: SiteRegistry,
    args: argparse.Namespace,
    client: PoliteClient,
    llm: Llm | None,
    search: WebSearch | None,
    store: SiteStore | None,
) -> tuple[BrandSite | None, int]:
    """브랜드로 수집할 사이트를 정한다. 못 정하면 (None, 종료 코드)."""
    listed = registry.find(args.brand)
    if listed is not None:
        site = _usable(listed, args.allow_disabled)
        return site, EXIT_OK if site else EXIT_USAGE
    settings = get_settings()
    resolution = await resolve_site(
        registry=registry,
        store=store or build_store(settings),
        client=client,
        llm=llm or get_catalog_llm(),
        search=search or GeminiSearch(settings),
        brand=args.brand,
        ttl_days=settings.catalog_site_ttl_days,
        negative_ttl_days=settings.catalog_site_negative_ttl_days,
    )
    for note in resolution.notes:
        print(note, file=sys.stderr)
    if resolution.site is None:
        print(
            f"{args.brand}: 수집할 공식 사이트를 정하지 못했다. {resolution.reason}",
            file=sys.stderr,
        )
        return None, EXIT_NOT_FOUND
    found = resolution.site
    print(f"사이트: {found.domain} (출처 {resolution.origin}, 정책 {found.policy})")
    site = _usable(found, args.allow_disabled)
    return site, EXIT_OK if site else EXIT_USAGE


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
    client: PoliteClient,
    llm: Llm,
    search: WebSearch,
    store: SiteStore,
    registry: SiteRegistry,
    args: argparse.Namespace,
) -> int:
    known = registry.find(args.brand)
    if known is not None:
        print(f"이미 목록에 있다: {known.brand} {known.domain or '-'}")
        return EXIT_OK
    found = await discover_and_admit(client, llm, search, args.brand, tuple(args.alias), args.hint)
    try:
        await store.save(found.record)
    except StoreError as error:
        print(f"찾은 사이트를 저장하지 못했다: {error}", file=sys.stderr)
    result = found.result
    print(f"status={result.status} method={result.method}")
    if result.search_error:
        print(f"검색 실패, 모델 제안으로 대신했다: {result.search_error}")
    for query in result.search_queries:
        print("검색어", query, sep="\t")
    for host, reason in result.rejected:
        print("제외", host, reason, sep="\t")
    for accepted in result.accepted:
        print("후보", accepted.host, accepted.site.platform, accepted.reason, sep="\t")
    for host, admission in found.admissions:
        print(f"admission={admission.reason}", host, admission.detail, sep="\t")
    record = found.record
    if record.status != "ADMITTED" or record.site is None:
        print(f"결과={record.status} {record.reason}")
        return EXIT_NOT_FOUND
    site = record.site
    if record.tie_break:
        print(
            f"수집할 수 있는 공식 사이트가 여럿이라 {record.tie_break} 규칙으로 골랐다: "
            f"{site.domain}"
        )
    lines = [
        "brand_sites.yaml에 더할 항목(robots만 기계로 확인한 상태로 켠다):",
        f"- brand: {site.brand}",
        f"  domain: {site.domain}",
        f"  language: {site.language}",
        f"  platform: {site.platform}",
        f'  technical: "{site.technical}"',
        f'  policy: "{site.policy}"',
        f"  enabled: {str(site.enabled).lower()}",
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
    *,
    type_hint: str | None = None,
    classify: bool = False,
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
            type_hint=type_hint,
            classify=classify,
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


async def upload_run(uploader: RunUploader, path: Path) -> bool:
    try:
        uploaded = await uploader.upload(path)
    except UploadError as error:
        print(
            f"S3에 올리지 못했다: {error}. 로컬 파일은 남아 있다. 다시 올리려면 upload {path}",
            file=sys.stderr,
        )
        return False
    manifest = uploaded.manifest
    print(f"S3에 올렸다: {uploaded.key} ({manifest['items']}건, 실패 {manifest['failed']}건)")
    return True


async def run_upload(uploader: RunUploader | None, files: list[Path]) -> int:
    if uploader is None:
        print("CATALOG_RUNS_STORE=s3와 CATALOG_RUNS_S3_BUCKET이 필요하다", file=sys.stderr)
        return EXIT_USAGE
    results = [await upload_run(uploader, path) for path in files]
    return EXIT_OK if all(results) else EXIT_STOPPED


def failed_urls(run_file: Path) -> list[str]:
    """실행 결과 파일 옆 체크포인트에 실패로 남은 상품 주소."""
    header, items = read_run_file(run_file)
    for _ in items:
        pass
    return Checkpoint.load_or_create(checkpoint_path_for(run_file), header.run_id).failed_keys()


async def run_collect(
    client: PoliteClient,
    site: BrandSite,
    args: argparse.Namespace,
    renderer: Renderer | None,
    llm: Llm | None,
    uploader: RunUploader | None = None,
) -> int:
    if args.resume and args.retry_of:
        print("--resume과 --retry-of는 함께 쓸 수 없다", file=sys.stderr)
        return EXIT_USAGE
    platform = await resolve_platform(client, site)
    candidates = read_candidates(args.products)
    if args.retry_of:
        try:
            failed = set(failed_urls(args.retry_of))
        except (RunFileError, CheckpointError, OSError) as error:
            print(f"다시 수집할 실행을 읽지 못했다: {error}", file=sys.stderr)
            return EXIT_USAGE
        candidates = [candidate for candidate in candidates if candidate.url in failed]
        if not candidates:
            print(f"{args.retry_of.name}에 다시 수집할 실패 상품이 없다", file=sys.stderr)
            return EXIT_USAGE
    if args.resume and uploader is not None:
        try:
            published = await uploader.is_published(args.resume)
        except UploadError as error:
            print(f"S3를 확인하지 못했다: {error}", file=sys.stderr)
            return EXIT_STOPPED
        if published:
            print(
                f"{args.resume.name}은 이미 S3에 올렸다. 올린 실행은 이어 쓰지 않는다. "
                f"실패한 상품은 --retry-of {args.resume}로 새 실행을 만든다",
                file=sys.stderr,
            )
            return EXIT_USAGE
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
                classify=args.classify,
                retry_failed=args.retry_failed,
                limit=args.limit,
            )
        except HttpFailure as error:
            print(f"{error.code}: {error} (그때까지 {writer.path} 에 저장했다)", file=sys.stderr)
            return EXIT_STOPPED
    print(f"{stats.written}건을 썼다, 실패 {len(stats.failed)}건, 건너뜀 {stats.skipped}건")
    print(f"실행 결과 파일: {writer.path}")
    if uploader is not None and not await upload_run(uploader, writer.path):
        return EXIT_STOPPED
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
    search: WebSearch | None,
    store: SiteStore | None,
    uploader: RunUploader | None,
) -> int:
    if args.command == "upload":
        return await run_upload(uploader, args.files)
    if args.command == "discover":
        try:
            return await run_discover(
                client,
                llm or get_catalog_llm(),
                search or GeminiSearch(get_settings()),
                store or build_store(get_settings()),
                registry,
                args,
            )
        except HttpFailure as error:
            print(f"{error.code}: {error}", file=sys.stderr)
            return EXIT_STOPPED
        except LlmError as error:
            print(f"모델 호출 실패({error.kind}): {error}", file=sys.stderr)
            return EXIT_STOPPED
        except StoreError as error:
            print(f"사이트 기록 저장소 설정 오류: {error}", file=sys.stderr)
            return EXIT_USAGE
    try:
        site, code = await _resolve_site(registry, args, client, llm, search, store)
    except HttpFailure as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return EXIT_STOPPED
    except LlmError as error:
        print(f"모델 호출 실패({error.kind}): {error}", file=sys.stderr)
        return EXIT_STOPPED
    except StoreError as error:
        print(f"사이트 기록 저장소 설정 오류: {error}", file=sys.stderr)
        return EXIT_USAGE
    if site is None:
        return code
    try:
        if args.command == "find":
            return await run_find(client, site, args.name)
        if args.command == "collect":
            needs_model = args.vision or args.estimate or args.classify
            model = (llm or get_catalog_llm()) if needs_model else None
            return await run_collect(client, site, args, renderer, model, uploader)
        if args.command == "product":
            needs_model = args.vision or args.estimate or args.classify
            model = (llm or get_catalog_llm()) if needs_model else None
            return await run_product(
                client,
                site,
                args.url,
                renderer,
                args.colors,
                model,
                args.estimate,
                type_hint=args.type,
                classify=args.classify,
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
    search: WebSearch | None = None,
    store: SiteStore | None = None,
    uploader: RunUploader | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        loaded = registry or load_registry()
    except RegistryError as error:
        print(f"사이트 목록 오류: {error}", file=sys.stderr)
        return EXIT_USAGE
    if args.command == "sites":
        return print_sites(loaded)
    if uploader is None and args.command in ("collect", "upload"):
        try:
            uploader = build_uploader(get_settings())
        except UploadError as error:
            print(f"결과 파일 업로드 설정 오류: {error}", file=sys.stderr)
            return EXIT_USAGE

    async def go() -> int:
        owned = client or PoliteClient(http_config(loaded))
        browser = renderer
        if browser is None and getattr(args, "render", False):
            browser = PlaywrightRenderer(owned)
        try:
            return await _run(args, loaded, owned, browser, llm, search, store, uploader)
        finally:
            if browser is not None and renderer is None:
                await browser.close()
            if client is None:
                await owned.aclose()

    return asyncio.run(go())


if __name__ == "__main__":
    sys.exit(main())
