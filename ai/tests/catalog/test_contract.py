import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from app.core.paths import CATALOG_IMPORT_DIR
from app.tasks.catalog.contract import (
    CollectedProduct,
    ColorSource,
    EvidenceRecord,
    RunItem,
    collected_product_schema,
    evidence_key,
)

SAMPLES = CATALOG_IMPORT_DIR / "samples"
SCHEMA_FILE = CATALOG_IMPORT_DIR / "collected_product.v1.schema.json"
VALID_SAMPLES = [
    "romand_single_unverified.json",
    "romand_duo_shade.json",
    "etude_option_image.json",
    "romand_named_palette.json",
]


def sample(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def changed(_file: str = "etude_option_image.json", **edits):
    data = sample(_file)
    for path, value in edits.items():
        target = data
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[int(key)] if key.isdigit() else target[key]
        last = keys[-1]
        if last.isdigit():
            target[int(last)] = value
        else:
            target[last] = value
    return data


def errors_of(data: dict) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        CollectedProduct.model_validate(data)
    return [".".join(str(p) for p in e["loc"]) + ": " + e["msg"] for e in caught.value.errors()]


@pytest.mark.parametrize("name", VALID_SAMPLES)
def test_shared_samples_are_accepted_and_round_trip_unchanged(name: str) -> None:
    data = sample(name)

    product = CollectedProduct.model_validate(data)

    assert json.loads(json.dumps(product.to_wire())) == data


def test_broken_sample_is_rejected_for_its_two_defects_only() -> None:
    problems = errors_of(sample("invalid_incomplete_source.json"))

    assert len(problems) == 2
    assert any(p.startswith("sourceProductId") for p in problems)
    assert any(p.startswith("shades.0.colors.0.hex") for p in problems)


@pytest.mark.parametrize("name", VALID_SAMPLES)
def test_json_schema_accepts_the_valid_samples(name: str) -> None:
    jsonschema.validate(sample(name), collected_product_schema())


def test_json_schema_rejects_the_broken_sample() -> None:
    validator = jsonschema.Draft202012Validator(collected_product_schema())

    paths = {
        ".".join(str(p) for p in e.absolute_path)
        for e in validator.iter_errors(sample("invalid_incomplete_source.json"))
    }

    assert "shades.0.colors.0.hex" in paths
    assert any(
        e.validator == "required"
        for e in validator.iter_errors(sample("invalid_incomplete_source.json"))
    )


def test_committed_json_schema_matches_the_model() -> None:
    committed = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))

    assert committed == collected_product_schema(), (
        "모델을 바꿨으면 uv run python tools/export_catalog_schema.py 로 파일을 갱신한다"
    )


def test_unknown_contract_version_is_rejected() -> None:
    assert any(p.startswith("contractVersion") for p in errors_of(changed(contractVersion=2)))


@pytest.mark.parametrize(
    "field", ["itemKey", "source", "sourceProductId", "sourceUrl", "collectedAt", "brand", "name"]
)
def test_required_product_fields(field: str) -> None:
    data = sample("etude_option_image.json")
    del data[field]

    assert any(p.startswith(field) for p in errors_of(data))


@pytest.mark.parametrize(
    "source", ["etude.com", "OFFICIAL:", "OFFICIAL:a.com/x", "OLIVE:oliveyoung.co.kr"]
)
def test_source_must_be_official_or_web_with_a_domain(source: str) -> None:
    assert any(p.startswith("source:") for p in errors_of(changed(source=source)))


def test_long_domain_source_fits() -> None:
    product = CollectedProduct.model_validate(changed(source="OFFICIAL:www.thesaemcosmetic.com"))

    assert len(product.source) == 32


def test_naive_datetime_is_rejected() -> None:
    assert any("시간대" in p for p in errors_of(changed(collectedAt="2026-11-05T10:32:00")))


def test_lengths_are_rejected_not_truncated() -> None:
    assert errors_of(changed(brand="b" * 101))
    assert errors_of(changed(name="n" * 201))
    assert errors_of(changed(**{"shades.0.name": "s" * 101}))


def test_blank_text_is_rejected() -> None:
    assert errors_of(changed(brand="   "))
    assert errors_of(changed(**{"shades.0.name": " "}))


def test_same_option_id_twice_is_rejected() -> None:
    data = sample("etude_option_image.json")
    data["shades"][1]["sourceOptionId"] = "01-black"
    data["shades"][1]["colors"][0]["evidenceKey"] = "example-curl-fix-mascara/01-black/1"

    assert any("옵션 값" in p for p in errors_of(data))


def test_evidence_key_must_be_built_from_product_option_and_slot() -> None:
    wrong = changed(**{"shades.0.colors.0.evidenceKey": "other/01-black/1"})

    assert any("evidenceKey" in p for p in errors_of(wrong))
    assert evidence_key("p", "o", 2) == "p/o/2"


def test_color_status_must_match_the_slots() -> None:
    assert any(
        "NOT_FOUND" in p for p in errors_of(changed(**{"shades.0.colorStatus": "NOT_FOUND"}))
    )
    empty = changed(**{"shades.0.colors": []})
    assert any("EXTRACTED" in p for p in errors_of(empty))


def test_slot_order_basis_is_required_with_slots_but_not_without() -> None:
    data = sample("etude_option_image.json")
    del data["shades"][0]["slotOrderBasis"]

    assert any("slotOrderBasis" in p for p in errors_of(data))
    colorless = sample("romand_single_unverified.json")
    del colorless["shades"][1]["slotOrderBasis"]
    CollectedProduct.model_validate(colorless)


def test_slot_orders_must_be_unique_in_a_shade() -> None:
    data = sample("romand_duo_shade.json")
    data["shades"][0]["colors"][1]["sortOrder"] = 1
    data["shades"][0]["colors"][1]["evidenceKey"] = "9002/01 예시 듀오 브라운/1"

    assert any("겹친다" in p for p in errors_of(data))


def test_slot_name_and_name_source_must_agree() -> None:
    base = "shades.0.colors.0."
    assert errors_of(changed(**{base + "name": "Sand"}))
    assert errors_of(changed(**{base + "nameSource": "SITE_TEXT"}))
    assert errors_of(changed(**{base + "name": "1", base + "nameSource": "MODEL_INDEX"}))
    named = changed(**{base + "name": "Sand", base + "nameSource": "IMAGE_PRINT"})
    assert CollectedProduct.model_validate(named).shades[0].colors[0].name == "Sand"


@pytest.mark.parametrize("hex_value", ["#1e1b1c", "1E1B1C", "#1E1B1", "#GGGGGG", "#1E1B1CFF"])
def test_hex_must_be_uppercase_rrggbb(hex_value: str) -> None:
    assert errors_of(changed(**{"shades.0.colors.0.hex": hex_value}))


def test_colorless_slot_keeps_source_and_quality_null() -> None:
    base = "shades.0.colors.0."
    colorless = changed(
        **{
            "shades.0.colorStatus": "FAILED",
            base + "hex": None,
            base + "colorSource": None,
            base + "colorQuality": None,
        }
    )
    CollectedProduct.model_validate(colorless)
    with_source = changed(**{"shades.0.colorStatus": "FAILED", base + "hex": None})
    assert any("색이 없는 칸" in p for p in errors_of(with_source))


def test_a_color_needs_its_source_and_link() -> None:
    base = "shades.0.colors.0."
    assert errors_of(changed(**{base + "colorSource": None}))
    assert errors_of(changed(**{base + "shadeLink": None}))
    assert errors_of(changed(**{base + "colorSource": "SAMPLE"}))
    assert errors_of(changed(**{base + "colorSource": "OFFICIAL"}))


def test_quality_rule_depends_on_the_color_source() -> None:
    base = "shades.0.colors.0."
    assert errors_of(changed(**{base + "colorQuality": None}))
    assert errors_of(changed(**{base + "colorQuality": 1.2}))
    for source in (ColorSource.SOURCE_VALUE, ColorSource.LLM_ESTIMATE):
        assert errors_of(changed(**{base + "colorSource": source.value}))
        ok = changed(**{base + "colorSource": source.value, base + "colorQuality": None})
        CollectedProduct.model_validate(ok)


def test_variant_hints_absence_is_kept_as_absence() -> None:
    data = sample("etude_option_image.json")
    del data["shades"][0]["variantHints"]

    product = CollectedProduct.model_validate(data)

    assert product.shades[0].variant_hints is None
    assert "variantHints" in product.to_wire()["shades"][0]
    assert product.to_wire()["shades"][0]["variantHints"] is None


def test_variant_hints_accept_origin_text_and_attributes() -> None:
    data = changed(
        **{
            "shades.0.variantHints": {
                "volume": "3.5g",
                "listPrice": "12000",
                "optionAttributes": {"용량": "본품"},
            }
        }
    )

    hints = CollectedProduct.model_validate(data).shades[0].variant_hints

    assert hints is not None
    assert hints.volume == "3.5g"
    assert hints.option_attributes == {"용량": "본품"}
    assert hints.composition is None


def test_run_item_keys_must_agree_and_evidence_must_point_at_a_slot() -> None:
    product = CollectedProduct.model_validate(sample("etude_option_image.json"))
    record = EvidenceRecord(
        evidence_key="example-curl-fix-mascara/01-black/1", method="pixel", method_version="1"
    )

    RunItem(item_key=product.item_key, collected=product, evidence=[record])
    with pytest.raises(ValidationError):
        RunItem(item_key="999999", collected=product)
    stray = EvidenceRecord(evidence_key="x/y/1", method="pixel", method_version="1")
    with pytest.raises(ValidationError):
        RunItem(item_key=product.item_key, collected=product, evidence=[stray])


def test_wire_format_is_camel_case_and_keeps_nulls() -> None:
    product = CollectedProduct.model_validate(sample("romand_named_palette.json"))
    wire = product.to_wire()

    assert wire["collectedAt"] == "2026-11-05T10:34:00+09:00"
    assert wire["shades"][0]["colors"][2]["hex"] is None
    assert "source_url" not in wire
    deep = copy.deepcopy(wire)
    assert datetime.fromisoformat(deep["collectedAt"]).astimezone(UTC) == datetime(
        2026, 11, 5, 1, 34, tzinfo=UTC
    )


def test_samples_directory_has_the_expected_files() -> None:
    names = {path.name for path in Path(SAMPLES).glob("*.json")}

    assert set(VALID_SAMPLES) | {"invalid_incomplete_source.json"} <= names
