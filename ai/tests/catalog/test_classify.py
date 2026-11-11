import json
import re
from pathlib import Path

import pytest

from app.clients.llm import LlmError
from app.core.paths import AI_DIR
from app.tasks.catalog.classify import (
    CLASSIFY_SYSTEM,
    PRODUCT_TYPES,
    TypeAnswer,
    TypeCode,
    add_type,
    normalize_type,
)
from app.tasks.catalog.runfile import read_run_file
from app.tasks.catalog.runner import read_candidates
from tests.catalog.helpers import make, run
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.catalog.test_estimate import product_of
from tests.catalog.test_report import chips_site, collect_args, products_file
from tests.fakes import FakeLlm

SEED = AI_DIR.parent / "backend/src/main/resources/db/seed/product-categories.sql"


def answer(code: str) -> TypeAnswer:
    return TypeAnswer(type_code=TypeCode(code))


@pytest.mark.skipif(not SEED.is_file(), reason="백엔드 시드 파일이 없는 환경")
def test_the_type_codes_match_the_backend_seed() -> None:
    text = SEED.read_text(encoding="utf-8")
    types = text[text.index("INSERT INTO product_types") :]
    seeded = dict(re.findall(r"\('([A-Z_]+)',\s*'([A-Z_]+)'", types))

    assert seeded == PRODUCT_TYPES


def test_a_type_from_the_input_is_used_without_asking_the_model() -> None:
    product, raw = product_of("Coral")
    llm = FakeLlm()

    typed, result = run(add_type(product, raw, given=" lip_tint ", llm=llm))

    assert (typed.type_hint, typed.category_hint) == ("LIP_TINT", "LIP")
    assert result["type"] == {"code": "LIP_TINT", "origin": "INPUT"}
    assert llm.calls == []
    assert typed.to_wire()["typeHint"] == "LIP_TINT"


def test_the_model_picks_a_type_when_the_input_has_none() -> None:
    product, raw = product_of("Coral", "Rose")
    llm = FakeLlm(answer("CUSHION"))

    typed, result = run(add_type(product, raw, llm=llm))

    assert (typed.type_hint, typed.category_hint) == ("CUSHION", "BASE")
    assert result["type"] == {"code": "CUSHION", "origin": "MODEL"}
    [call] = llm.calls
    assert call.system == CLASSIFY_SYSTEM and call.images == []
    assert product.name in call.text and "Coral, Rose" in call.text
    assert "LIP_TINT" in call.text and "UNKNOWN" in call.text


def test_an_unknown_input_type_falls_back_to_the_model_with_a_warning() -> None:
    product, raw = product_of("Coral")

    typed, _ = run(add_type(product, raw, given="LIPPY", llm=FakeLlm(answer("LIP_GLOSS"))))

    assert typed.type_hint == "LIP_GLOSS"
    assert "INVALID_TYPE_HINT" in typed.warnings
    assert normalize_type("LIPPY") is None and normalize_type(None) is None


def test_unknown_or_failed_classification_leaves_the_type_empty() -> None:
    product, raw = product_of("Coral")

    unknown, unknown_raw = run(add_type(product, raw, llm=FakeLlm(answer("UNKNOWN"))))
    failed, failed_raw = run(
        add_type(product, raw, llm=FakeLlm(LlmError("retryable", "시간 초과")))
    )

    assert (unknown.type_hint, unknown.category_hint) == (None, None)
    assert "TYPE_UNKNOWN" in unknown.warnings
    assert unknown_raw["type"] == {"code": None, "origin": "MODEL"}
    assert failed.type_hint is None and "CLASSIFY_FAILED:retryable" in failed.warnings
    assert "type" not in failed_raw


def test_without_input_or_model_nothing_changes() -> None:
    product, raw = product_of("Coral")

    same, same_raw = run(add_type(product, raw))

    assert same == product and same_raw == raw


def test_the_model_can_only_answer_known_codes() -> None:
    with pytest.raises(ValueError):
        TypeAnswer.model_validate({"type_code": "LIP_STAIN"})


def test_candidates_may_carry_a_type(tmp_path: Path) -> None:
    path = tmp_path / "p.jsonl"
    path.write_text(
        json.dumps({"url": "https://a/1", "title": "t", "product_id": "1", "type_hint": "CUSHION"})
        + "\n"
        + json.dumps({"url": "https://a/2", "title": "t", "product_id": "2"}),
        encoding="utf-8",
    )

    first, second = read_candidates(path)

    assert (first.type_hint, second.type_hint) == ("CUSHION", None)


def typed_products_file(tmp_path: Path, type_hint: str | None) -> Path:
    path = products_file(tmp_path, "1170")
    data = json.loads(path.read_text(encoding="utf-8"))
    if type_hint:
        data["type_hint"] = type_hint
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def collected(tmp_path: Path):
    [path] = sorted((tmp_path / "runs").glob("*.jsonl"))
    _, items = read_run_file(path)
    [item] = list(items)
    return item.collected


def test_collect_sends_the_type_from_the_products_file(tmp_path: Path) -> None:
    client, _ = make(chips_site())
    llm = FakeLlm()

    code = cli.main(
        collect_args(tmp_path, typed_products_file(tmp_path, "LIP_TINT"), "--classify"),
        registry=enabled_registry(tmp_path),
        client=client,
        llm=llm,
    )

    assert code == 0 and llm.calls == []
    assert (collected(tmp_path).type_hint, collected(tmp_path).category_hint) == (
        "LIP_TINT",
        "LIP",
    )


def test_collect_classifies_only_when_asked(tmp_path: Path) -> None:
    llm = FakeLlm(answer("LIP_TINT"))
    off = tmp_path / "off"
    on = tmp_path / "on"
    off.mkdir()
    on.mkdir()

    cli.main(
        collect_args(off, typed_products_file(off, None)),
        registry=enabled_registry(off),
        client=make(chips_site())[0],
        llm=llm,
    )
    cli.main(
        collect_args(on, typed_products_file(on, None), "--classify"),
        registry=enabled_registry(on),
        client=make(chips_site())[0],
        llm=llm,
    )

    assert collected(off).type_hint is None
    assert collected(on).type_hint == "LIP_TINT"
    assert len(llm.calls) == 1
