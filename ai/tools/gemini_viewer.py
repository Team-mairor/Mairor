"""Gemini 영상 시험 확인 화면 (개발용).

Gemini에 무엇을 보냈고 무엇을 돌려받았는지, 그 결과가 AI 서버 입력과 가이드로 어떻게 바뀌는지
단계별로 본다. 결과 파일은 tools/gemini_video_test.py run으로 만든다.

실행 (ai/ 폴더에서): uv run streamlit run tools/gemini_viewer.py
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
# streamlit은 스크립트 폴더(tools/)만 import 경로에 넣어서, app 패키지를 찾게 ai/를 더한다
sys.path.insert(0, str(AI_ROOT))

import altair as alt
import pandas as pd
import streamlit as st
from gemini_video_test import RUNS_DIR, parse_time, to_guide_input, video_id_of
from pydantic import ValidationError

from app.schemas.guide import GuideInput
from app.services.guide_builder import build_guide

# 유튜브 페이지의 실제 길이. 사람이 나눈 구간이 있는 영상은 samples 폴더를 같이 쓴다
VIDEO_LENGTHS = {"eFzG30avtOI": 525}
HUMAN_SAMPLES = {"eFzG30avtOI": "local_01"}

FACT_FIELDS = ["area", "tool", "amount", "strength", "finishCue", "tips", "cautions"]
FIELD_LABELS = {
    "area": "바르는 곳",
    "tool": "도구",
    "amount": "양",
    "strength": "세기",
    "finishCue": "끝내는 기준",
    "tips": "팁",
    "cautions": "주의점",
}
SOURCE_LABELS = {"voice": "음성", "onscreenText": "화면 글자", "scene": "장면", "estimated": "추정"}
BAR_COLOR = "#2a78d6"


# ---------- 읽기·바꾸기 ----------


def load_runs() -> dict[str, dict]:
    """파일 이름 = <영상 ID>_<회차>.json"""
    runs = {}
    paths = sorted(
        RUNS_DIR.glob("*_*.json"),
        key=lambda p: (p.stem.rsplit("_", 1)[0], int(p.stem.rsplit("_", 1)[1])),
    )
    for path in paths:
        run = json.loads(path.read_text(encoding="utf-8"))
        asked = "MM:SS로" if "MM:SS" in run["prompt"] else "초 숫자로"
        extra = " + 브랜드 칸" if '"brand"' in json.dumps(run["schema"]) else ""
        video_id, number = path.stem.rsplit("_", 1)
        run["path"] = path
        run["videoId"] = video_id_of(run["videoUrl"])
        runs[f"{video_id} {number}회차 · 시각을 {asked} 요청{extra}"] = run
    return runs


def mmss(sec: float | None) -> str:
    if sec is None:
        return "-"
    return f"{int(sec) // 60:02d}:{int(sec) % 60:02d}"


def pick(obj: dict, *keys):
    return next((obj[k] for k in keys if k in obj), None)


def convert_steps(run: dict) -> list[dict]:
    """Gemini 단계 → 초로 바꾼 값 + 검사 문제를 붙인 보기용 단계."""
    length = VIDEO_LENGTHS.get(run["videoId"])
    steps = []
    for raw in run["output"]["steps"]:
        problems = []
        start_raw = pick(raw, "startTime", "startSeconds")
        end_raw = pick(raw, "endTime", "endSeconds")
        start, p1 = parse_time(start_raw)
        end, p2 = parse_time(end_raw)
        problems += [f"구간 {p}" for p in (p1, p2) if p]
        if start is not None and end is not None and end <= start:
            problems.append("끝이 시작보다 빠름")
        if length and end is not None and end > length:
            problems.append(f"끝 {end:g}초가 영상 길이({length}초) 밖")

        def in_range(sec, start=start, end=end):
            return start is not None and end is not None and start <= sec <= end

        keyframes = []
        for k in pick(raw, "keyframeTimes", "keyframeSeconds") or []:
            sec, p = parse_time(k)
            if p:
                problems.append(f"대표 장면 {p}")
            elif not in_range(sec):
                problems.append(f"대표 장면 {mmss(sec)}가 구간 밖")
            keyframes.append({"raw": k, "sec": sec})

        facts = []
        for field in FACT_FIELDS:
            value = (raw.get("facts") or {}).get(field)
            for item in value if isinstance(value, list) else [value] if value else []:
                at, p = parse_time(item.get("at"))
                if p:
                    problems.append(f"{FIELD_LABELS[field]} 근거 시각 {p}")
                ok = at is None or in_range(at)
                if not ok:
                    problems.append(f"{FIELD_LABELS[field]} 근거 시각 {mmss(at)}가 구간 밖")
                facts.append(
                    {**item, "field": field, "atRaw": item.get("at"), "at": at, "inRange": ok}
                )

        steps.append(
            {
                "raw": raw,
                "order": raw["order"],
                "part": raw.get("partLabel") or "",
                "makeup": raw["makeup"],
                "summary": raw.get("summary") or "",
                "product": raw.get("product"),
                "start": start,
                "end": end,
                "startRaw": start_raw,
                "endRaw": end_raw,
                "keyframes": keyframes,
                "facts": facts,
                "problems": problems,
            }
        )
    return steps


def human_steps(video_id: str) -> list[dict]:
    sample = HUMAN_SAMPLES.get(video_id)
    if not sample:
        return []
    manifest = json.loads(
        (AI_ROOT / "samples" / sample / "manifest.json").read_text(encoding="utf-8")
    )
    return [
        {
            "order": s["order"],
            "part": "",
            "makeup": s["makeup"],
            "start": s["startSeconds"],
            "end": s["endSeconds"],
        }
        for s in manifest["steps"]
    ]


def product_text(product: dict | None) -> str:
    if not product or not product.get("name"):
        return "확인 안 됨"
    brand = f"[{product['brand']}] " if product.get("brand") else ""
    shade = f" / {product['shade']}" if product.get("shade") else ""
    source = SOURCE_LABELS.get(product.get("source"), product.get("source") or "")
    palette = product.get("palette")
    color = f" · 고른 색: {palette['color']['value']}" if isinstance(palette, dict) else ""
    return f"{brand}{product['name']}{shade} ({source}){color}"


def set_seek(key: str, sec: float) -> None:
    st.session_state[key] = sec


# ---------- 화면 ----------

st.set_page_config(page_title="Gemini 영상 시험", layout="wide")
st.title("Gemini 영상 시험 확인")
st.caption(
    "유튜브 URL + 프롬프트 → **Gemini** → 단계 목록 JSON → 시각을 초로 바꿈 (BE가 할 일) → "
    "**AI 서버 입력** (docs/GUIDE_INPUT.md) → 문장 틀 생성기 → **가이드**"
)

runs = load_runs()
# 처음 열면 시각을 제대로 받은(MM:SS) 실행 중 가장 최근 것을 보여 준다
latest_ok = max((i for i, r in enumerate(runs.values()) if "MM:SS" in r["prompt"]), default=0)
choice = st.sidebar.radio("시험 결과", list(runs), index=latest_ok)
run = runs[choice]
steps = convert_steps(run)
length = VIDEO_LENGTHS.get(run["videoId"])

usage = run["usage"]
by_kind = {d["modality"]: d["tokenCount"] for d in usage.get("promptTokensDetails", [])}
with st.sidebar:
    st.metric("걸린 시간", f"{run['elapsedSeconds']:.0f}초")
    st.metric("입력 토큰", f"{usage['promptTokenCount']:,}")
    st.caption(
        f"영상 {by_kind.get('VIDEO', 0):,} · 음성 {by_kind.get('AUDIO', 0):,} · "
        f"글 {by_kind.get('TEXT', 0):,}"
    )
    st.metric("출력 토큰", f"{usage.get('candidatesTokenCount', 0):,}")
    st.caption(f"생각 토큰 {usage.get('thoughtsTokenCount', 0):,} · 모델 `{run['model']}`")
    st.caption(f"파일: {run['path'].relative_to(AI_ROOT).as_posix()}")

if "MM:SS" not in run["prompt"]:
    st.warning(
        "이 실행은 시각을 '초'로 달라고 했는데, Gemini가 322(=3분 22초)처럼 분초 숫자로 답했어요. "
        "아래 값은 분초로 보고 바꾼 거예요. 받은 숫자를 초 그대로 쓰면 마지막 단계가 835초가 되어 "
        f"{length}초짜리 영상 밖으로 나가요."
    )

ai_input = to_guide_input(run, length)
ai_steps = {s["stepId"]: s for s in ai_input["steps"]}
try:
    build = build_guide(GuideInput.model_validate(ai_input))
    guide_steps = {g.step_id: g for g in build.guide.steps}
    input_errors = []
except ValidationError as e:
    guide_steps = {}
    input_errors = [
        {"칸": ".".join(map(str, err["loc"])), "이유": err["msg"]} for err in e.errors()
    ]

sent, by_step, compare = st.tabs(["① Gemini 요청과 응답", "② 단계별로 보기", "③ 실행끼리 비교"])

with sent:
    request_col, response_col = st.columns(2)
    with request_col:
        st.subheader("요청 (보낸 것)")
        st.video(run["videoUrl"])
        st.caption(f"{run['videoUrl']} · 실제 길이 {mmss(length)} ({length}초)")
        st.markdown(
            f"`{run['model']}`에 HTTP 요청 한 번을 보냈어요. "
            "영상 파일은 올리지 않고 **유튜브 URL만** 넣었어요."
        )
        # gemini_video_test.py가 보낸 본문 모양. 긴 두 칸은 아래에 따로 펼친다
        st.json(
            {
                "contents": [
                    {
                        "parts": [
                            {"fileData": {"fileUri": run["videoUrl"]}},
                            {"text": "(아래 프롬프트)"},
                        ]
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": "(아래 응답 형식)",
                    "temperature": 0.2,
                },
            }
        )
        with st.expander("프롬프트", expanded=True):
            st.code(run["prompt"], language=None, wrap_lines=True)
        with st.expander("응답 형식: 이 모양의 JSON으로만 답하게 강제함"):
            st.json(run["schema"], expanded=False)

    with response_col:
        st.subheader("응답 (돌려받은 것)")
        st.markdown(
            "응답 형식을 강제해서 Gemini는 글 대신 **JSON 하나**로 답해요. "
            "아래 시각은 Gemini가 쓴 그대로예요 (아직 초로 안 바꿈)."
        )
        st.caption(
            f"끝난 이유 {run['finishReason']} · "
            f"출력 토큰 {usage.get('candidatesTokenCount', 0):,} · "
            f"단계 {len(run['output']['steps'])}개 · "
            f"영상 길이 {pick(run['output'], 'duration', 'durationSeconds')}"
        )
        st.dataframe(
            [
                {
                    "단계": s["order"],
                    "부위 이름": s.get("partLabel"),
                    "분류": s["makeup"],
                    "시작": str(pick(s, "startTime", "startSeconds")),
                    "끝": str(pick(s, "endTime", "endSeconds")),
                    "제품": product_text(s.get("product")),
                    "요약": s.get("summary"),
                }
                for s in run["output"]["steps"]
            ],
            hide_index=True,
            column_config={
                "제품": st.column_config.TextColumn(width="medium"),
                "요약": st.column_config.TextColumn(width="large"),
            },
        )
        st.markdown("**받은 JSON 원본** · 단계를 펼치면 사실 칸(facts)·대표 장면·제품이 보여요")
        st.json(run["output"], expanded=2)

with by_step:
    if input_errors:
        st.error("이 실행 결과는 AI 서버 입력 검사에서 거절돼요. 그래서 가이드가 안 만들어져요.")
        st.dataframe(input_errors, hide_index=True)

    overview = [
        {
            "단계": s["order"],
            "부위 이름": s["part"],
            "분류": s["makeup"],
            "구간": f"{mmss(s['start'])}~{mmss(s['end'])}",
            "길이(초)": None if s["start"] is None or s["end"] is None else s["end"] - s["start"],
            "제품": product_text(s["product"]),
            "대표 장면": len(s["keyframes"]),
            "채운 칸": sum(1 for f in FACT_FIELDS if any(x["field"] == f for x in s["facts"])),
            "문제": len(s["problems"]),
        }
        for s in steps
    ]
    st.caption(
        "행을 누르면 아래에 그 단계가 펼쳐져요. "
        "'채운 칸'은 도구·양·세기·끝내는 기준·팁·주의점 6칸 중 몇 칸이 나왔는지예요."
    )
    event = st.dataframe(
        overview,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"steps:{choice}",
        column_config={
            "채운 칸": st.column_config.ProgressColumn(
                min_value=0, max_value=len(FACT_FIELDS), format=f"%d/{len(FACT_FIELDS)}"
            )
        },
    )
    rows = event.selection.rows
    step = steps[rows[0] if rows else 0]
    ai_step = ai_steps[f"s{step['order']}"]

    st.divider()
    st.subheader(f"{step['order']}. {step['part']}  ·  `{step['makeup']}`")
    for problem in step["problems"]:
        st.warning(problem)

    video_col, gemini_col, ai_col = st.columns([1.1, 1.3, 1])

    with video_col:
        st.markdown("**영상에서 확인**")
        seek_key = f"seek:{choice}:{step['order']}"
        seek = st.session_state.get(seek_key, step["start"] or 0)
        end_time = int(step["end"]) + 1 if step["end"] and seek < step["end"] else None
        st.video(run["videoUrl"], start_time=int(seek), end_time=end_time)
        st.caption(f"재생 시작 {mmss(seek)} · 단계 구간 {mmss(step['start'])}~{mmss(step['end'])}")
        st.button(
            "단계 처음부터",
            on_click=set_seek,
            args=(seek_key, step["start"] or 0),
            key=f"start:{seek_key}",
        )

        st.markdown("**대표 장면** · BE가 이 시각을 캡처해 이미지 주소(images)로 넘길 자리")
        cols = st.columns(3)
        for i, k in enumerate(step["keyframes"]):
            cols[i % 3].button(
                f"🖼 {mmss(k['sec'])}",
                on_click=set_seek,
                args=(seek_key, k["sec"] or 0),
                key=f"kf:{seek_key}:{i}",
                width="stretch",
            )

        with_at = [f for f in step["facts"] if f["at"] is not None]
        if with_at:
            st.markdown("**근거 시각으로 이동**")
            cols = st.columns(2)
            for i, f in enumerate(with_at):
                mark = "" if f["inRange"] else " ⚠"
                cols[i % 2].button(
                    f"▶ {FIELD_LABELS[f['field']]} {mmss(f['at'])}{mark}",
                    on_click=set_seek,
                    args=(seek_key, f["at"]),
                    key=f"at:{seek_key}:{i}",
                    width="stretch",
                )

    with gemini_col:
        st.markdown("**Gemini가 돌려준 것**")
        st.markdown(f"요약: {step['summary']}")
        st.markdown(f"제품: {product_text(step['product'])}")

        st.markdown("**뽑힌 사실** · 값 (출처 · 근거 시각)")
        lines = []
        for field in FACT_FIELDS:
            items = [f for f in step["facts"] if f["field"] == field]
            if not items:
                lines.append(f"- **{FIELD_LABELS[field]}**: :gray[(없음)]")
            for f in items:
                where = SOURCE_LABELS.get(f["source"], f["source"])
                if f["at"] is not None:
                    where += f" · {mmss(f['at'])}" + ("" if f["inRange"] else " :orange[⚠ 구간 밖]")
                lines.append(f"- **{FIELD_LABELS[field]}**: {f['value']} :gray[({where})]")
        st.markdown("\n".join(lines))

        times = (
            [
                {"무엇": "시작", "Gemini가 쓴 값": str(step["startRaw"]), "초": step["start"]},
                {"무엇": "끝", "Gemini가 쓴 값": str(step["endRaw"]), "초": step["end"]},
            ]
            + [
                {"무엇": f"대표 장면 {i + 1}", "Gemini가 쓴 값": str(k["raw"]), "초": k["sec"]}
                for i, k in enumerate(step["keyframes"])
            ]
            + [
                {
                    "무엇": f"{FIELD_LABELS[f['field']]} 근거",
                    "Gemini가 쓴 값": str(f["atRaw"]),
                    "초": f["at"],
                }
                for f in step["facts"]
                if f["atRaw"] is not None
            ]
        )
        with st.expander("시각을 초로 바꾼 과정"):
            st.dataframe(times, hide_index=True)
        with st.expander("이 단계 원본 JSON"):
            st.json(step["raw"])

    with ai_col:
        st.markdown("**AI 서버 입력으로 바뀐 모습**")
        st.caption("형식 = `app/schemas/guide.py`의 GuideInputStep · 이미지 주소는 예시")
        st.json(ai_step, expanded=True)
        if (step["product"] or {}).get("source"):
            st.caption("product.source(제품 출처)는 입력 형식에 없어서 버려요.")

        st.markdown("**지금 생성기로 만든 가이드** (문장 틀, LLM 없음)")
        guide = guide_steps.get(ai_step["stepId"])
        if guide is None:
            st.info("입력 검사에서 거절돼서 가이드가 없어요.")
        else:
            st.markdown(f"##### {guide.order}. {guide.title}")
            for sentence in guide.instructions:
                st.markdown(f"- {sentence}")
            for tip in guide.tips:
                st.markdown(f"💡 {tip}")
            for caution in guide.cautions:
                st.markdown(f"⚠️ {caution}")
            if guide.missing_fields:
                st.badge(
                    "미확인: " + ", ".join(FIELD_LABELS.get(f, f) for f in guide.missing_fields),
                    color="gray",
                )

with compare:
    st.markdown(
        "**단계 경계** · 막대 하나가 단계 하나예요. "
        "위아래 막대 경계가 맞으면 실행마다 같게 나눈 거예요."
    )
    timeline = []
    human = human_steps(run["videoId"])
    labels = (["사람이 나눈 구간 (local_01)"] if human else []) + list(runs)
    for label, rows_ in [("사람이 나눈 구간 (local_01)", human)] + [
        (label, convert_steps(r)) for label, r in runs.items()
    ]:
        for s in rows_:
            if s["start"] is None or s["end"] is None or s["end"] <= s["start"]:
                continue
            timeline.append(
                {
                    "실행": label,
                    "단계": s["order"],
                    "부위 이름": s["part"],
                    "분류": s["makeup"],
                    "구간": f"{mmss(s['start'])}~{mmss(s['end'])}",
                    "시작": s["start"],
                    # 이웃 막대 사이에 틈을 둬서 경계가 보이게 한다
                    "끝(그림)": max(s["start"] + 0.5, s["end"] - 1.5),
                }
            )
    chart = (
        alt.Chart(pd.DataFrame(timeline))
        .mark_bar(color=BAR_COLOR, cornerRadius=3, height=20)
        .encode(
            x=alt.X("시작:Q", title="영상 시각 (초)", scale=alt.Scale(domain=[0, length or 600])),
            x2="끝(그림):Q",
            y=alt.Y("실행:N", title=None, sort=labels, axis=alt.Axis(labelLimit=260)),
            tooltip=["실행", "단계", "부위 이름", "분류", "구간"],
        )
        .properties(height=48 * len(labels))
    )
    st.altair_chart(chart, width="stretch")

    st.markdown(
        f"**분류 비교** · '{choice}'의 단계마다, "
        "그 단계 가운데 시각을 다른 실행은 어떻게 분류했는지예요."
    )
    others = {label: convert_steps(r) for label, r in runs.items() if label != choice}

    def covering(rows_: list[dict], sec: float) -> str:
        hit = next(
            (
                s
                for s in rows_
                if s["start"] is not None and s["end"] is not None and s["start"] <= sec <= s["end"]
            ),
            None,
        )
        return f"{hit['makeup']} · {hit['part']}" if hit else "(단계 없음)"

    compare_rows = []
    for s in steps:
        if s["start"] is None or s["end"] is None:
            continue
        mid = (s["start"] + s["end"]) / 2
        row = {
            "구간": f"{mmss(s['start'])}~{mmss(s['end'])}",
            choice: f"{s['makeup']} · {s['part']}",
        }
        row.update({label: covering(r, mid) for label, r in others.items()})
        same = {v.split(" · ")[0] for k, v in row.items() if k != "구간"}
        row["분류 같음"] = "✓" if len(same) == 1 else "다름"
        compare_rows.append(row)
    st.dataframe(compare_rows, hide_index=True)

    st.markdown("**칸 채움** · 전체 단계 중 그 칸이 나온 단계 수")
    fill = []
    for label, r in runs.items():
        rs = convert_steps(r)
        row = {"실행": label}
        for f in FACT_FIELDS:
            row[FIELD_LABELS[f]] = (
                f"{sum(1 for s in rs if any(x['field'] == f for x in s['facts']))}/{len(rs)}"
            )
        row["제품"] = f"{sum(1 for s in rs if (s['product'] or {}).get('name'))}/{len(rs)}"
        row["브랜드"] = f"{sum(1 for s in rs if (s['product'] or {}).get('brand'))}/{len(rs)}"
        row["문제"] = sum(len(s["problems"]) for s in rs)
        fill.append(row)
    st.dataframe(fill, hide_index=True)
