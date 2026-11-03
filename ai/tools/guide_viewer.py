"""가이드 생성 확인 화면 (개발용). 입력 칸이 어떤 문장 틀을 거쳐 어떤 가이드가 되는지 본다.

실행 (ai/ 폴더에서): uv run streamlit run tools/guide_viewer.py
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
# streamlit은 스크립트 폴더(tools/)만 import 경로에 넣어서, app 패키지를 찾게 ai/를 더한다
sys.path.insert(0, str(AI_ROOT))

import streamlit as st
from pydantic import ValidationError

from app.schemas.guide import FieldTrace, GuideBuild, GuideInput
from app.tasks.template_guide.guide_builder import build_guide

SAMPLES_DIR = AI_ROOT / "samples"
CASES_DIR = AI_ROOT / "tests" / "golden" / "guide"

FIELD_LABELS = {
    "tool": "도구",
    "amount": "양",
    "strength": "세기",
    "finishCue": "끝내는 기준",
    "tips": "팁",
    "cautions": "주의점",
}
STATUS_LABELS = {"used": "사용", "estimated": "추정", "missing": "미확인", "empty": "없음"}
SOURCE_LABELS = {"voice": "음성", "onscreenText": "화면 글자", "scene": "장면", "estimated": "추정"}
TRACE_COLUMNS = {
    "받은 값 (출처 · 근거 시각)": st.column_config.TextColumn(width="medium"),
    "만든 문장": st.column_config.TextColumn(width="medium"),
}


def load_sources() -> dict[str, Path]:
    cases = {f"저장된 케이스 / {p.stem}": p for p in sorted(CASES_DIR.glob("*.json"))}
    samples = {
        f"samples / {p.parent.name}": p for p in sorted(SAMPLES_DIR.glob("*/guide_input.json"))
    }
    return cases | samples


def read_input(path: Path) -> tuple[dict, dict | None]:
    """(입력, 저장된 기대값). samples의 입력은 기대값이 없다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if path.parent == CASES_DIR:
        return data["input"], data["expected"]
    return data, None


def dump_guide(build: GuideBuild) -> dict:
    return build.guide.model_dump(mode="json", by_alias=True, exclude_none=True)


def label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def received(t: FieldTrace) -> str:
    if t.value is None:
        return ""
    where = SOURCE_LABELS[t.source] + (f" {t.at:g}초" if t.at is not None else "")
    return f"{t.value} ({where})"


def show_trace(build: GuideBuild, steps_by_id: dict) -> None:
    for step_trace in build.trace:
        step = steps_by_id[step_trace.step_id]
        guide_step = next(s for s in build.guide.steps if s.step_id == step_trace.step_id)
        st.markdown(
            f"**{guide_step.order}. {guide_step.title}** · `{step.step_id}` · `{step.makeup}` · "
            f"{step.start_seconds:g}~{step.end_seconds:g}초"
        )
        # 빈 값은 표에 None으로 찍히지 않게 빈 문자열로 둔다
        rows = [
            {
                "칸": label(t.field),
                "상태": STATUS_LABELS[t.status],
                "받은 값 (출처 · 근거 시각)": received(t),
                "만든 문장": t.sentence or "",
                "문장 틀": t.template_id or "",
            }
            for t in step_trace.fields
        ]
        st.dataframe(rows, hide_index=True, width="stretch", column_config=TRACE_COLUMNS)


def show_guide(build: GuideBuild) -> None:
    for step in build.guide.steps:
        st.subheader(f"{step.order}. {step.title}")
        for sentence in step.instructions:
            st.markdown(f"- {sentence}")
        for tip in step.tips:
            st.markdown(f"💡 {tip}")
        for caution in step.cautions:
            st.markdown(f"⚠️ {caution}")
        if step.estimated_fields:
            st.badge("추정: " + ", ".join(map(label, step.estimated_fields)), color="orange")
        if step.missing_fields:
            st.badge("미확인: " + ", ".join(map(label, step.missing_fields)), color="gray")


def save_case(name: str, raw_input: dict, expected: dict) -> Path:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    path = CASES_DIR / f"{name}.json"
    case = {"input": raw_input, "expected": expected}
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


st.set_page_config(page_title="가이드 생성 확인", layout="wide")
st.title("가이드 생성 확인")

sources = load_sources()
choice = st.sidebar.selectbox("입력 불러오기", list(sources))
loaded_input, saved_expected = read_input(sources[choice])

left, middle, right = st.columns([1, 2, 1.1])

with left:
    st.header("입력")
    text = st.text_area(
        "BE가 넘기는 JSON (docs/GUIDE_INPUT.md)",
        value=json.dumps(loaded_input, ensure_ascii=False, indent=2),
        height=700,
        key=f"input:{choice}",
    )

try:
    raw_input = json.loads(text)
    guide_input = GuideInput.model_validate(raw_input)
except json.JSONDecodeError as e:
    middle.error(f"JSON 문법 오류: {e}")
    st.stop()
except ValidationError as e:
    middle.error("입력이 규격과 다릅니다.")
    middle.dataframe(
        [{"칸": ".".join(map(str, err["loc"])), "이유": err["msg"]} for err in e.errors()],
        hide_index=True,
        width="stretch",
    )
    st.stop()

build = build_guide(guide_input)
current = dump_guide(build)

with middle:
    st.header("과정")
    show_trace(build, {step.step_id: step for step in guide_input.steps})

with right:
    st.header("결과")
    if saved_expected is not None:
        if saved_expected == current:
            st.success("저장된 기대값과 같아요.")
        else:
            st.warning("저장된 기대값과 달라요. 의도한 변경이면 다시 저장하세요.")
    show_guide(build)
    with st.expander("결과 JSON"):
        st.json(current)

with st.sidebar:
    st.divider()
    default_name = sources[choice].stem if saved_expected else guide_input.video_id
    name = st.text_input("케이스 이름", value=default_name)
    if st.button("이 결과를 기대값으로 저장", type="primary"):
        path = save_case(name, raw_input, current)
        st.success(f"저장함: {path.relative_to(AI_ROOT)}")
        st.caption("uv run pytest 가 이 케이스로 결과를 비교합니다.")
