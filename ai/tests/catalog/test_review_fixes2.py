from app.tasks.catalog.discover.registry import (
    BrandSite,
    Platform,
    Policy,
    SiteRegistry,
    Technical,
)
from app.tasks.catalog.http import HttpConfig
from tests.catalog.test_checkpoint_and_cli import cli


def site(brand: str, domain: str | None, *, exempt: bool, policy: Policy) -> BrandSite:
    return BrandSite(
        brand=brand,
        domain=domain,
        language="ko",
        platform=Platform.CAFE24,
        technical=Technical.OK if domain else Technical.NO,
        policy=policy,
        enabled=policy is not Policy.UNCONFIRMED,
        robots_exempt=exempt,
    )


def test_the_registry_lists_the_domains_marked_robots_exempt() -> None:
    registry = SiteRegistry(
        [
            site("가", "Allowed.Example", exempt=True, policy=Policy.PERMISSION),
            site("나", "other.example", exempt=False, policy=Policy.PERMISSION),
            site("다", "terms.example", exempt=False, policy=Policy.TERMS_CHECKED),
            site("라", None, exempt=False, policy=Policy.UNCONFIRMED),
        ]
    )

    assert registry.robots_exempt_hosts() == frozenset({"allowed.example"})


def test_robots_exemption_needs_a_permission_record() -> None:
    import pytest

    with pytest.raises(ValueError):
        site("가", "x.example", exempt=True, policy=Policy.TERMS_CHECKED)


def test_the_cli_http_config_merges_settings_and_the_site_list(monkeypatch) -> None:
    monkeypatch.setenv("CATALOG_ROBOTS_EXEMPT_HOSTS", '["From.Settings"]')
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        registry = SiteRegistry(
            [site("가", "listed.example", exempt=True, policy=Policy.PERMISSION)]
        )

        config = cli.http_config(registry)
    finally:
        get_settings.cache_clear()

    assert isinstance(config, HttpConfig)
    assert config.robots_exempt_hosts == frozenset({"from.settings", "listed.example"})


def test_without_any_exemption_the_config_exempts_nothing() -> None:
    registry = SiteRegistry([site("가", "a.example", exempt=False, policy=Policy.TERMS_CHECKED)])

    assert cli.http_config(registry).robots_exempt_hosts == frozenset()
