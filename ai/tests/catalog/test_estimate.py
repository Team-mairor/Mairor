import json
from datetime import UTC, datetime

import httpx2
import pytest

from app.clients.llm import LlmError
from app.tasks.catalog.color.estimate import ESTIMATE_SYSTEM, Estimate, Estimates, add_estimates
from app.tasks.catalog.contract import ColorSource, ColorStatus, NameSource, ShadeLink
from app.tasks.catalog.discover.registry import Platform
from app.tasks.catalog.extract.collect import collect_product
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, Site, make, run
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.catalog.test_extract import site_of
from tests.catalog.test_vision import shopify, variant
from tests.fakes import FakeLlm

NOW = datetime(2026, 11, 5, tzinfo=UTC)


def product_of(*titles: str):
    return shopify([variant(i, title) for i, title in enumerate(titles, start=1)], [])


def estimate(llm, product, raw):
    return run(add_estimates(llm, product, raw))


def reply(*pairs: tuple[str, str | None]) -> Estimates:
    return Estimates(items=[Estimate(option_id=o, hex=h) for o, h in pairs])


def test_named_shades_get_a_model_estimate_and_others_stay_without_color() -> None:
    product, raw = product_of("Coral", "01")
    llm = FakeLlm(reply(("1", "#e8836b"), ("2", None)))

    estimated, result = estimate(llm, product, raw)

    coral, number = estimated.shades
    [color] = coral.colors
    assert coral.color_status is ColorStatus.EXTRACTED
    assert color.hex == "#E8836B"
    assert color.color_source is ColorSource.LLM_ESTIMATE
    assert color.shade_link is ShadeLink.UNVERIFIED
    assert color.color_quality is None
    assert color.name_source is NameSource.NONE
    assert (number.color_status, number.colors) == (ColorStatus.NOT_FOUND, [])
    assert "LLM_ESTIMATE_USED" in estimated.warnings
    assert result["estimate"]["asked"] == 2 and result["estimate"]["answered"] == 1
    [record] = result["evidence"]
    assert record["method"] == "llm_estimate" and record["imageUrl"] is None
    assert estimated.to_wire()["shades"][0]["colors"][0]["colorSource"] == "LLM_ESTIMATE"


def test_only_well_formed_answers_for_asked_shades_are_used() -> None:
    product, raw = product_of("Coral", "Rose", "Nude")
    llm = FakeLlm(
        reply(("1", "red"), ("2", "#12345"), ("9", "#AABBCC"), ("3", "#C8A08A"), ("3", "#000000"))
    )

    estimated, _ = estimate(llm, product, raw)

    assert [s.color_status for s in estimated.shades] == [
        ColorStatus.NOT_FOUND,
        ColorStatus.NOT_FOUND,
        ColorStatus.EXTRACTED,
    ]
    assert estimated.shades[2].colors[0].hex == "#C8A08A"


def test_the_prompt_lists_names_without_images_and_tells_the_model_not_to_guess() -> None:
    product, raw = product_of("Coral", "01")
    llm = FakeLlm(reply())

    estimate(llm, product, raw)

    [call] = llm.calls
    assert call.images == []
    assert "option_id=1 / 이름=Coral" in call.text and "Dear Dahlia" not in call.text
    assert "null" in ESTIMATE_SYSTEM and "짐작하지 않는다" in call.system


def test_shades_that_already_have_colors_or_failed_are_left_alone() -> None:
    product, raw = product_of("Coral", "Rose", "Nude")
    done, failed, open_ = product.shades
    kept = done.model_copy(
        update={
            "color_status": ColorStatus.FAILED,
        }
    )
    product = product.model_copy(
        update={
            "shades": [kept, failed.model_copy(update={"color_status": ColorStatus.FAILED}), open_]
        }
    )
    llm = FakeLlm(reply(("1", "#111111"), ("2", "#222222"), ("3", "#333333")))

    estimated, _ = estimate(llm, product, raw)

    assert [s.color_status for s in estimated.shades[:2]] == [ColorStatus.FAILED] * 2
    assert "option_id=3" in llm.calls[0].text and "option_id=1" not in llm.calls[0].text
    assert estimated.shades[2].colors[0].hex == "#333333"


def test_without_candidates_the_model_is_not_called() -> None:
    product, raw = product_of("Coral")
    product = product.model_copy(
        update={
            "shades": [
                s.model_copy(update={"color_status": ColorStatus.FAILED}) for s in product.shades
            ]
        }
    )
    llm = FakeLlm()

    estimated, _ = estimate(llm, product, raw)

    assert llm.calls == [] and estimated == product


def test_a_model_failure_leaves_the_product_as_it_was() -> None:
    product, raw = product_of("Coral")

    estimated, result = estimate(FakeLlm(LlmError("retryable", "x")), product, raw)

    assert estimated.shades[0].colors == []
    assert "ESTIMATE_FAILED:retryable" in estimated.warnings
    assert "estimate" not in result


# --- 수집에 끼우기 ---


def collect(llm, **kwargs):
    data = json.dumps(
        {
            "id": 1,
            "title": "Tint",
            "options": [{"name": "Shade"}],
            "images": [],
            "variants": [variant(1, "Coral"), variant(2, "Rose")],
        }
    )
    site = Site(
        {
            f"{HOST}/products/tint": lambda: httpx2.Response(
                200, text=fixtures.SHOPIFY_PRODUCT, headers=HTML
            ),
            f"{HOST}/products/tint.js": lambda: httpx2.Response(200, text=data),
        }
    )
    client, _ = make(site)

    async def go():
        async with client:
            return await collect_product(
                client,
                site_of(Platform.SHOPIFY),
                Platform.SHOPIFY,
                f"https://{HOST}/products/tint",
                item_key="000001",
                now=NOW,
                llm=llm,
                **kwargs,
            )

    return run(go())


def test_estimates_are_off_unless_asked_for() -> None:
    llm = FakeLlm()

    product, _ = collect(llm)

    assert llm.calls == [] and all(s.colors == [] for s in product.shades)


def test_estimates_run_when_asked_for_and_a_model_is_given() -> None:
    llm = FakeLlm(reply(("1", "#E8836B"), ("2", "#C9707A")))

    product, raw = collect(llm, estimate=True)

    assert [s.colors[0].color_source for s in product.shades] == [ColorSource.LLM_ESTIMATE] * 2
    assert raw["estimate"]["answered"] == 2


def test_asking_for_estimates_without_a_model_does_nothing() -> None:
    product, _ = collect(None, estimate=True)

    assert all(s.colors == [] for s in product.shades)


def test_product_command_estimate_flag(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    data = json.dumps(
        {
            "id": 1,
            "title": "Tint",
            "options": [],
            "images": [],
            "variants": [variant(1, "Coral"), variant(2, "Rose")],
        }
    )
    client, _ = make(
        Site(
            {
                f"{HOST}/products/tint": lambda: httpx2.Response(
                    200, text=fixtures.SHOPIFY_PRODUCT, headers=HTML
                ),
                f"{HOST}/products/tint.js": lambda: httpx2.Response(200, text=data),
            }
        )
    )
    registry = enabled_registry(tmp_path)
    registry = type(registry)([registry.sites[0].model_copy(update={"platform": Platform.SHOPIFY})])

    code = cli.main(
        ["product", "--brand", "테스트", "--url", f"https://{HOST}/products/tint", "--estimate"],
        registry=registry,
        client=client,
        llm=FakeLlm(reply(("1", "#E8836B"))),
    )

    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert printed["collected"]["shades"][0]["colors"][0]["colorSource"] == "LLM_ESTIMATE"
    assert printed["raw"]["estimate"]["asked"] == 2
