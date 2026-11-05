from pathlib import Path

import pytest
import yaml

from app.tasks.catalog.discover.registry import (
    DEFAULT_SITES_FILE,
    Platform,
    Policy,
    RegistryError,
    Technical,
    load_registry,
)
from app.tasks.catalog.text import compact_key, normalize_name, tokens


def write(tmp_path: Path, sites: list[dict]) -> Path:
    path = tmp_path / "sites.yaml"
    path.write_text(yaml.safe_dump(sites, allow_unicode=True), encoding="utf-8")
    return path


def site(**overrides) -> dict:
    base = {"brand": "테스트", "domain": "test.example", "language": "ko"}
    return {**base, **overrides}


def test_bundled_list_loads_with_the_researched_brands() -> None:
    registry = load_registry()

    assert len(registry.sites) == 26
    assert registry.find("롬앤").source == "OFFICIAL:romand.co.kr"
    assert registry.find("Romand").platform is Platform.CAFE24
    assert registry.find("에뛰드").platform is Platform.WOOCOMMERCE
    assert registry.find("DEAR DAHLIA").language == "en"
    assert registry.find("러브라이너").language == "ja"


def test_every_site_starts_unconfirmed_and_off() -> None:
    registry = load_registry()

    assert all(s.policy is Policy.UNCONFIRMED for s in registry.sites)
    assert all(not s.enabled for s in registry.sites)
    assert registry.enabled_sites() == ()
    assert all(not s.robots_exempt for s in registry.sites)


def test_sites_without_an_official_home_cannot_be_collected() -> None:
    registry = load_registry()

    for brand in ("컬러그램", "웨이크메이크"):
        found = registry.find(brand)
        assert found.domain is None
        assert found.technical is Technical.NO
        assert not found.can_collect


def test_brands_sharing_a_home_share_the_source() -> None:
    registry = load_registry()

    assert registry.find("페리페라").source == registry.find("클리오").source


def test_brand_lookup_ignores_case_spaces_and_punctuation() -> None:
    registry = load_registry()

    for query in ("The Saem", "thesaem", "더 샘", "더샘", "  THE-SAEM "):
        assert registry.find(query).brand == "더샘", query
    assert registry.find("3ce").brand == "3CE"
    assert registry.find("없는 브랜드") is None
    assert registry.find("   ") is None


def test_the_default_file_is_inside_the_app_package() -> None:
    assert DEFAULT_SITES_FILE.exists()
    assert DEFAULT_SITES_FILE.parent.name == "resources"


def test_a_site_cannot_be_enabled_before_its_policy_is_confirmed(tmp_path: Path) -> None:
    path = write(tmp_path, [site(enabled=True, technical="OK")])

    with pytest.raises(RegistryError, match="정책 확인"):
        load_registry(path)


@pytest.mark.parametrize("policy", ["TERMS_CHECKED", "PERMISSION"])
def test_a_confirmed_collectable_site_can_be_enabled(tmp_path: Path, policy: str) -> None:
    registry = load_registry(write(tmp_path, [site(enabled=True, technical="OK", policy=policy)]))

    assert registry.enabled_sites()[0].brand == "테스트"


def test_a_site_that_cannot_be_collected_cannot_be_enabled(tmp_path: Path) -> None:
    path = write(tmp_path, [site(enabled=True, policy="PERMISSION", technical="NO")])

    with pytest.raises(RegistryError, match="수집할 수 없는"):
        load_registry(path)


def test_robots_exemption_needs_a_permission_record(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="허락 기록"):
        load_registry(write(tmp_path, [site(robots_exempt=True, policy="TERMS_CHECKED")]))
    allowed = load_registry(write(tmp_path, [site(robots_exempt=True, policy="PERMISSION")]))
    assert allowed.sites[0].robots_exempt


def test_a_missing_domain_requires_technical_no(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="도메인"):
        load_registry(write(tmp_path, [site(domain=None, technical="OK")]))
    load_registry(write(tmp_path, [site(domain=None, technical="NO")]))


def test_search_path_needs_the_query_placeholder(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="query"):
        load_registry(write(tmp_path, [site(search_path="/search")]))


def test_duplicate_names_are_rejected(tmp_path: Path) -> None:
    path = write(tmp_path, [site(aliases=["foo"]), site(brand="다른", aliases=["Foo"])])

    with pytest.raises(RegistryError, match="겹친다"):
        load_registry(path)


def test_malformed_files_are_rejected(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("{ not: [valid", encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(broken)
    with pytest.raises(RegistryError):
        load_registry(tmp_path / "missing.yaml")
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text("brand: x", encoding="utf-8")
    with pytest.raises(RegistryError, match="배열"):
        load_registry(mapping)


def test_name_helpers() -> None:
    assert normalize_name("  쥬시   래스팅\t틴트 ") == "쥬시 래스팅 틴트"
    assert compact_key("[롬앤] 쥬시-래스팅 틴트") == "롬앤쥬시래스팅틴트"
    assert compact_key("Dear.A") == "deara"
    assert tokens("쥬시 래스팅-틴트 01") == {"쥬시", "래스팅", "틴트", "01"}
