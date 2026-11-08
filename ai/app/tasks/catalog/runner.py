"""상품 후보 목록을 돌며 상품을 수집해 실행 결과 파일에 쓴다.

상품 하나가 끝날 때마다 줄을 쓰고 체크포인트를 저장하므로 끊겨도 이어서 할 수 있다.
상품 단위로 실패해도 다음으로 넘어가지만, 봇 차단(BLOCKED)은 그 사이트의 수집을 멈추기 위해 올린다.
체크포인트의 키는 상품 주소다. evidence는 raw에서 꺼내 줄의 evidence[]로 올린다.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.clients.llm import Llm
from app.tasks.catalog.checkpoint import Checkpoint
from app.tasks.catalog.contract import EvidenceRecord, RunHeader, RunItem
from app.tasks.catalog.discover.registry import BrandSite, Platform
from app.tasks.catalog.extract.collect import collect_product
from app.tasks.catalog.extract.product import ExtractError
from app.tasks.catalog.find.urls import Candidate
from app.tasks.catalog.http import BlockedError, HttpFailure, PoliteClient
from app.tasks.catalog.render.browser import Renderer
from app.tasks.catalog.runfile import RunFileWriter

COLLECTOR_VERSION = "0.1.0"


@dataclass
class RunStats:
    written: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    skipped: int = 0


def new_header(site: BrandSite) -> RunHeader:
    return RunHeader(
        run_id=uuid4().hex,
        started_at=datetime.now(UTC),
        seed=site.source,
        collector_version=COLLECTOR_VERSION,
    )


def read_candidates(path: Path) -> list[Candidate]:
    """list 명령이 쓴 JSONL(상품 후보)을 읽는다. 같은 상품 번호는 한 번만 둔다."""
    seen: set[str] = set()
    found: list[Candidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        candidate = Candidate(url=data["url"], title=data["title"], product_id=data["product_id"])
        if candidate.product_id not in seen:
            seen.add(candidate.product_id)
            found.append(candidate)
    return found


async def collect_candidates(
    client: PoliteClient,
    site: BrandSite,
    platform: Platform,
    candidates: Iterable[Candidate],
    writer: RunFileWriter,
    checkpoint: Checkpoint,
    *,
    renderer: Renderer | None = None,
    colors: bool = False,
    llm: Llm | None = None,
    estimate: bool = False,
    retry_failed: bool = False,
    limit: int | None = None,
) -> RunStats:
    """후보마다 상품을 수집해 파일에 쓴다. BlockedError는 올린다(그때까지의 줄은 이미 저장됐다)."""
    stats = RunStats()
    by_url = {candidate.url: candidate for candidate in candidates}
    pending = checkpoint.pending(list(by_url), retry_failed=retry_failed)
    stats.skipped = len(by_url) - len(pending)
    for url in pending[:limit]:
        try:
            product, raw = await collect_product(
                client,
                site,
                platform,
                url,
                item_key=writer.next_item_key(),
                renderer=renderer,
                colors=colors,
                llm=llm,
                estimate=estimate,
            )
        except BlockedError:
            raise
        except (ExtractError, HttpFailure) as error:
            code = getattr(error, "code", "ERROR")
            checkpoint.mark_failed(url, code)
            stats.failed[url] = code
            continue
        evidence = [EvidenceRecord.model_validate(entry) for entry in raw.pop("evidence", [])]
        writer.append(
            RunItem(item_key=product.item_key, collected=product, evidence=evidence, raw=raw)
        )
        checkpoint.mark_done(url)
        stats.written += 1
    return stats
