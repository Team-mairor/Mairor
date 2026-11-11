import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.clients.object_store import S3ObjectStore
from app.core.config import Settings
from app.core.paths import DEFAULT_CATALOG_SITES_DIR
from app.tasks.catalog.discover.registry import BrandSite, Platform, Policy, Technical
from app.tasks.catalog.discover.site_store import (
    LocalSiteStore,
    S3SiteStore,
    SiteRecord,
    StoreError,
    build_store,
    new_record,
    record_key,
)
from tests.fakes import FakeS3

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def admitted_site() -> BrandSite:
    return BrandSite(
        brand="어뮤즈",
        domain="amusemakeup.com",
        language="ko",
        platform=Platform.CAFE24,
        technical=Technical.PARTIAL,
        policy=Policy.ROBOTS_CHECKED,
        enabled=True,
    )


def record(**kwargs) -> SiteRecord:
    values = {
        "status": "ADMITTED",
        "site": admitted_site(),
        "method": "SEARCH",
        "queries": ("어뮤즈 공식 온라인 쇼핑몰",),
        "candidates": ("amusemakeup.com",),
        "tie_break": "KOREAN_SITE",
        "reason": "robots 허용",
        "now": NOW,
    }
    return new_record("어뮤즈", ("Amuse",), **(values | kwargs))


def denied(operation: str) -> ClientError:
    return ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, operation)


def run(coro):
    return asyncio.run(coro)


def test_the_key_ignores_spaces_case_and_symbols_and_is_safe_for_files() -> None:
    assert record_key("Dear.A") == record_key("dear a") == record_key("DEARA")
    assert "/" not in record_key("a/b") and ".." not in record_key("../x")


def test_a_record_is_found_by_the_brand_and_by_every_alias(tmp_path: Path) -> None:
    store = LocalSiteStore(tmp_path)

    run(store.save(record()))

    for name in ("어뮤즈", "Amuse", " AMUSE "):
        found = run(store.load(name))
        assert found is not None and found.site.domain == "amusemakeup.com"
    assert run(store.load("다른 브랜드")) is None
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        [record_key("어뮤즈"), record_key("Amuse")]
    )


def test_the_site_survives_a_round_trip_still_on_and_collectable(tmp_path: Path) -> None:
    store = LocalSiteStore(tmp_path)
    run(store.save(record()))

    loaded = run(store.load("어뮤즈"))

    assert loaded.site == admitted_site()
    assert loaded.site.policy is Policy.ROBOTS_CHECKED
    assert loaded.site.can_collect
    assert (loaded.method, loaded.tie_break) == ("SEARCH", "KOREAN_SITE")
    assert loaded.queries == ("어뮤즈 공식 온라인 쇼핑몰",)
    assert loaded.checked_at == NOW


def test_saving_again_replaces_the_record_and_leaves_no_temp_files(tmp_path: Path) -> None:
    store = LocalSiteStore(tmp_path)
    run(store.save(record()))

    run(store.save(record(status="REJECTED", site=None, reason="ROBOTS_DISALLOWS_PRODUCTS")))

    assert run(store.load("amuse")).status == "REJECTED"
    assert not list(tmp_path.glob("*.tmp"))


def test_a_corrupted_record_is_a_store_error_not_a_crash(tmp_path: Path) -> None:
    (tmp_path / record_key("어뮤즈")).write_text("{깨진", encoding="utf-8")

    with pytest.raises(StoreError):
        run(LocalSiteStore(tmp_path).load("어뮤즈"))


def test_a_blank_name_is_never_found_or_written(tmp_path: Path) -> None:
    assert run(LocalSiteStore(tmp_path).load("  ")) is None
    assert run(S3SiteStore(S3ObjectStore(FakeS3(), "b"), "p/").load("")) is None


@pytest.mark.parametrize(
    ("status", "age_days", "fresh"),
    [
        ("ADMITTED", 29, True),
        ("ADMITTED", 30, False),
        ("REJECTED", 6, True),
        ("REJECTED", 7, False),
        ("NOT_FOUND", 6, True),
        ("AMBIGUOUS", 8, False),
    ],
)
def test_admitted_records_last_longer_than_rejections(
    status: str, age_days: int, fresh: bool
) -> None:
    item = record(status=status, site=admitted_site() if status == "ADMITTED" else None)

    later = NOW + timedelta(days=age_days)

    assert item.is_fresh(later, ttl_days=30, negative_ttl_days=7) is fresh


def test_s3_stores_one_json_object_per_name_under_the_prefix() -> None:
    client = FakeS3()
    store = S3SiteStore(S3ObjectStore(client, "mairor-prod-media"), "catalog-sites")

    run(store.save(record()))

    keys = sorted(key for _, key in client.objects)
    assert keys == sorted(
        [f"catalog-sites/{record_key('어뮤즈')}", f"catalog-sites/{record_key('Amuse')}"]
    )
    assert {content_type for _, content_type in client.objects.values()} == {"application/json"}
    assert run(store.load("amuse")).site.domain == "amusemakeup.com"
    assert run(store.load("없는 브랜드")) is None


def test_s3_read_and_write_failures_are_store_errors_without_leaking_details() -> None:
    client = FakeS3()
    store = S3SiteStore(S3ObjectStore(client, "b"), "p/")
    client.get_error = denied("GetObject")
    client.put_error = EndpointConnectionError(endpoint_url="https://s3.example")

    with pytest.raises(StoreError) as read_error:
        run(store.load("어뮤즈"))
    with pytest.raises(StoreError) as write_error:
        run(store.save(record()))

    assert "AccessDenied" not in str(read_error.value)
    assert "s3.example" not in str(write_error.value)


def test_a_corrupted_s3_object_is_a_store_error() -> None:
    client = FakeS3()
    client.objects[("b", "p/" + record_key("어뮤즈"))] = (b"not json", "application/json")

    with pytest.raises(StoreError):
        run(S3SiteStore(S3ObjectStore(client, "b"), "p/").load("어뮤즈"))


def test_the_store_defaults_to_its_own_folder_apart_from_the_run_files() -> None:
    settings = Settings(_env_file=None)

    assert settings.catalog_sites_dir == DEFAULT_CATALOG_SITES_DIR
    assert settings.catalog_sites_dir != settings.catalog_run_dir
    assert DEFAULT_CATALOG_SITES_DIR.name == "catalog-sites"
    assert settings.catalog_sites_s3_prefix == "catalog-sites/"


def test_the_local_store_writes_to_the_configured_folder(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, catalog_sites_dir=tmp_path / "sites-here")

    store = build_store(settings)

    assert isinstance(store, LocalSiteStore)
    run(store.save(record()))
    assert (tmp_path / "sites-here" / record_key("어뮤즈")).is_file()


def test_s3_needs_a_bucket() -> None:
    with pytest.raises(StoreError):
        build_store(Settings(_env_file=None, catalog_sites_store="s3"))


def test_s3_is_built_with_the_configured_bucket_prefix_and_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def fake_client(service: str, region_name: str):
        seen.update(service=service, region=region_name)
        return FakeS3()

    import boto3

    monkeypatch.setattr(boto3, "client", fake_client)
    settings = Settings(
        _env_file=None,
        catalog_sites_store="s3",
        catalog_sites_s3_bucket="mairor-prod-media",
        catalog_sites_s3_prefix="catalog-sites/",
    )

    store = build_store(settings)

    assert isinstance(store, S3SiteStore)
    assert seen == {"service": "s3", "region": "ap-northeast-2"}
