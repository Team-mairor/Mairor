"""단계 설명 모델 비교 확인 화면 (개발용).

같은 단계 입력을 모델마다 어떻게 설명했는지 나란히 보고, 검사에 걸린 문장·시간·토큰을 비교한다.
결과 파일은 tools/explain_compare.py로 만든다.

실행 (ai/ 폴더에서): uv run streamlit run tools/explain_viewer.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
# streamlit은 스크립트 폴더(tools/)만 import 경로에 넣어서, app 패키지를 찾게 ai/를 더한다
sys.path.insert(0, str(AI_ROOT))

import streamlit as st
from explain_compare import RUNS_DIR, gms_usage, sentences_of

PROVIDER_LABELS = {"gpt": "GPT", "gemini": "Gemini", "claude": "Claude"}
PROBLEM_KINDS = ["길이", "개수", "근거", "숫자", "제품 이름", "도구 이름", "도구", "방향", "말투"]
PROBLEM_HELP = {
    "길이": "동작 25자·팁 30자를 넘음 (띄어쓰기 포함)",
    "개수": "동작이 1~4개가 아니거나 팁이 2개를 넘음",
    "근거": "근거 번호가 없거나 입력에 없는 번호",
    "숫자": "문장의 숫자가 근거로 단 입력에 없음",
    "제품 이름": "문장에 제품·브랜드·색상 이름이 들어감",
    "도구 이름": "화면에 따로 보이는 단계 도구를 문장에 씀",
    "도구": "입력 어디에도 없는 도구 이름",
    "방향": "근거 글과 반대 방향 (안쪽↔바깥쪽 등)",
    "말투": "해요체로 끝나지 않음",
}
TIP_LABELS = {"tip": ":blue-background[요령]", "caution": ":orange-background[주의]"}


# ---------- 읽기 ----------


def load_runs() -> dict[str, dict]:
    """파일 이름 = <영상 ID>_<회차>.json. 최근 실행이 위로 온다"""
    runs = {}
    paths = sorted(
        RUNS_DIR.glob("*_*.json"),
        key=lambda p: (p.stem.rsplit("_", 1)[0], int(p.stem.rsplit("_", 1)[1])),
        reverse=True,
    )
    for path in paths:
        run = json.loads(path.read_text(encoding="utf-8"))
        video_id, number = path.stem.rsplit("_", 1)
        run["path"] = path
        # 요금표가 없는 예전 결과는 지금 요금표로 계산한다
        for call in run["calls"]:
            call["gmsUsage"] = gms_usage(call["model"], call.get("tokens"), run.get("prices"))
        when = run["createdAt"][5:16].replace("T", " ")
        runs[f"{video_id} {number}회차 · 프롬프트 {run['promptVersion']} · {when}"] = run
    return runs


def product_text(product: dict | None) -> str:
    if not product:
        return "(없음)"
    parts = (product.get("brand"), product.get("name"), product.get("shade"))
    return " · ".join(part for part in parts if part)


def total(calls: list[dict], kind: str) -> int:
    return sum((c.get("tokens") or {}).get(kind, 0) for c in calls)


# 프롬프트 v1(하는 법·팁·주의 칸)과 v2(동작 + 동작에 붙은 팁) 결과를 같은 표로 비교하려고 쓴다
def actions_of(output: dict) -> list[dict]:
    return output["actions"] if "actions" in output else output["instructions"]


def tips_of(output: dict) -> list[dict]:
    if "actions" in output:
        return [action["tip"] for action in output["actions"] if action["tip"]]
    return output["tips"] + output["cautions"]


def done_when_of(output: dict) -> dict | None:
    return output.get("doneWhen") if "actions" in output else output.get("finishCue")


# ---------- 그리기 ----------


def render_output(call: dict | None, show_cost: bool = True) -> None:
    """모델 하나가 만든 단계 설명. 문장 뒤 회색 글자는 글자 수와 모델이 단 근거 번호."""
    if call is None:
        st.caption("이 실행에서 부르지 않음")
        return
    if call["error"]:
        st.error(call["error"])
        return
    if show_cost:
        tokens = call["tokens"]
        st.caption(
            f"{call['seconds']}초 · 입력 {tokens['input']:,} · 출력 {tokens['output']:,} · "
            f"생각 {tokens['thinking']:,} 토큰 · GMS {call['gmsUsage']:.1f}"
        )
    flagged = {p["text"] for p in call["problems"]}

    def line(sentence: dict, prefix: str) -> str:
        mark = ":orange[⚠] " if sentence["text"] in flagged else ""
        sources = ", ".join(sentence["sources"]) or "근거 없음"
        return f"{prefix}{mark}{sentence['text']} :gray[{len(sentence['text'])}자 · {sources}]"

    output = call["output"]
    if "actions" in output:
        # 단계 화면 아래에 보일 모양 그대로: 동작 목록, 그 동작에 붙은 팁, 넘어갈 때
        with st.container(border=True):
            lines = []
            for i, action in enumerate(output["actions"], 1):
                lines.append(line(action, f"{i}. "))
                if action["tip"]:
                    lines.append(line(action["tip"], f"    - {TIP_LABELS[action['tip']['kind']]} "))
            st.markdown("\n".join(lines))
            if output["doneWhen"]:
                st.markdown(line(output["doneWhen"], ":green-background[넘어갈 때] "))
        render_problems(call)
        return

    st.markdown("**하는 법**")
    st.markdown("\n".join(line(s, f"{i}. ") for i, s in enumerate(output["instructions"], 1)))
    for title, key in (("팁", "tips"), ("주의", "cautions")):
        if output[key]:
            st.markdown(f"**{title}**")
            st.markdown("\n".join(line(s, "- ") for s in output[key]))
    if output.get("finishCue"):
        st.markdown("**끝내는 기준**")
        st.markdown(line(output["finishCue"], "- "))
    render_problems(call)


def render_problems(call: dict) -> None:
    for p in call["problems"]:
        st.warning(f"**{p['kind']}** · {p['detail']}  \n{p['where']}: {p['text']}")
    unused = call["output"]["unused"]
    if unused:
        with st.expander(f"안 쓴 입력 {len(unused)}개"):
            st.markdown("\n".join(f"- `{u['id']}` {u['reason']}" for u in unused))


def render_inputs(step: dict) -> None:
    st.markdown(f"제품: {product_text(step['product'])}")
    st.caption("제품은 모델에 따로 주지 않고, 화면에 이 값을 그대로 보여 줄 자리예요.")
    st.markdown("\n".join(f"- `{key}` {value}" for key, value in step["inputs"].items()))


# ---------- 화면 ----------

st.set_page_config(page_title="단계 설명 모델 비교", layout="wide")
st.title("단계 설명 모델 비교")
st.caption(
    "가이드 입력(BE가 넘긴 단계 글) → 근거 시각으로 팁 자리 정리 → 모델마다 같은 프롬프트로 "
    "**쉬운 설명** 생성 → 코드 검사. 이미지는 보내지 않아요."
)

runs = load_runs()
if not runs:
    st.info("결과가 없어요. `uv run python tools/explain_compare.py`로 먼저 만드세요.")
    st.stop()

choice = st.sidebar.radio("실행 결과", list(runs))
run = runs[choice]
providers = list(run["models"])
calls = {(c["provider"], c["stepId"]): c for c in run["calls"]}
steps = run["steps"]

with st.sidebar:
    st.metric("전체 걸린 시간", f"{run['elapsedSeconds']:.0f}초")
    st.caption(f"단계 {len(steps)}개 × 모델 {len(providers)}개 · 동시에 여러 개 호출")
    for provider in providers:
        mine = [c for c in run["calls"] if c["provider"] == provider]
        actual = ", ".join(sorted({c["modelVersion"] for c in mine if c.get("modelVersion")}))
        usage = sum(c["gmsUsage"] for c in mine)
        st.caption(
            f"**{PROVIDER_LABELS[provider]}** `{run['models'][provider]}` → 실제 `{actual or '-'}`"
            f"  \nGMS 사용량 약 **{usage:,.0f}**"
        )
    st.caption("GMS 사용량 = 공개 요금(달러) × 10,000. GMS 사이트 숫자와 같은 단위예요.")
    st.caption(f"파일: {run['path'].relative_to(AI_ROOT).as_posix()}")

by_step, summary, whole, prompt_tab = st.tabs(
    ["① 단계별 비교", "② 모델별 요약", "③ 한 모델로 전체 읽기", "④ 프롬프트와 입력 정리"]
)

with by_step:
    overview = []
    for step in steps:
        row = {"단계": step["order"], "이름": step["partLabel"], "입력 수": len(step["inputs"])}
        for provider in providers:
            call = calls.get((provider, step["stepId"]))
            label = PROVIDER_LABELS[provider]
            if call is None or call["error"]:
                row[f"{label} 문장"], row[f"{label} 문제"] = None, "오류" if call else "-"
            else:
                row[f"{label} 문장"] = len(sentences_of(call["output"]))
                row[f"{label} 문제"] = str(len(call["problems"]) or "")
        overview.append(row)
    st.caption(
        "행을 누르면 아래에 그 단계가 펼쳐져요. '입력 수'는 모델에 준 줄 수(summary·도구·팁 등), "
        "'문장'은 모델이 쓴 동작·팁·넘어갈 때 문장 수예요."
    )
    event = st.dataframe(
        overview,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"steps:{choice}",
    )
    rows = event.selection.rows
    step = steps[rows[0] if rows else 0]

    st.divider()
    st.subheader(f"{step['order']}. {step['partLabel']}  ·  `{step['makeup']}`")
    columns = st.columns([1.1] + [1] * len(providers))
    with columns[0]:
        st.markdown("**입력 (모델에 보낸 것)**")
        render_inputs(step)
        with st.expander("실제로 보낸 메시지"):
            st.code(step["message"], language=None, wrap_lines=True)
    for column, provider in zip(columns[1:], providers, strict=True):
        with column:
            st.markdown(f"**{PROVIDER_LABELS[provider]}** `{run['models'][provider]}`")
            render_output(calls.get((provider, step["stepId"])))
            call = calls.get((provider, step["stepId"]))
            if call and call["output"]:
                with st.expander("받은 JSON 원본"):
                    st.json(call["output"])

with summary:
    st.caption(
        "검사는 코드로 잡을 수 있는 것만 봐요. 뜻이 바뀐 문장, 쓰지 말라고 한 상식이 들어간 "
        "문장은 ①에서 눈으로 봐야 해요. 토큰과 GMS 사용량은 이 실행의 단계를 모두 더한 값이고, "
        "생각 토큰도 출력 요금으로 계산돼요. GPT는 공개 요금으로 계산한 값이 GMS 사이트보다 "
        "적게 나와서(231 vs 404) 실제로는 더 들 수 있어요."
    )
    table = []
    for provider in providers:
        mine = [c for c in run["calls"] if c["provider"] == provider]
        done = [c for c in mine if not c["error"]]
        kinds = Counter(p["kind"] for c in done for p in c["problems"])
        seconds = [c["seconds"] for c in done]
        usage = sum(c["gmsUsage"] for c in mine)
        row = {
            "모델": f"{PROVIDER_LABELS[provider]} ({run['models'][provider]})",
            "성공": f"{len(done)}/{len(mine)}",
            "GMS 사용량": round(usage),
            "단계당 GMS": round(usage / max(len(mine), 1), 1),
            "문제 합계": sum(kinds.values()),
            **{kind: kinds.get(kind, 0) for kind in PROBLEM_KINDS},
            "동작 평균": round(
                sum(len(actions_of(c["output"])) for c in done) / max(len(done), 1), 1
            ),
            "가장 긴 동작(자)": max(
                (len(a["text"]) for c in done for a in actions_of(c["output"])), default=0
            ),
            "팁 합계": sum(len(tips_of(c["output"])) for c in done),
            "넘어갈 때 단계": sum(1 for c in done if done_when_of(c["output"])),
            "평균 초": round(sum(seconds) / max(len(seconds), 1), 1),
            "최대 초": max(seconds, default=0),
            "입력 토큰": total(mine, "input"),
            "출력 토큰": total(mine, "output"),
            "생각 토큰": total(mine, "thinking"),
        }
        table.append(row)
    st.dataframe(
        table,
        hide_index=True,
        column_config={
            kind: st.column_config.NumberColumn(help=PROBLEM_HELP[kind]) for kind in PROBLEM_KINDS
        },
    )

    problems = [
        {
            "모델": PROVIDER_LABELS[c["provider"]],
            "단계": next(s["order"] for s in steps if s["stepId"] == c["stepId"]),
            "종류": p["kind"],
            "내용": p["detail"],
            "칸": p["where"],
            "문장": p["text"],
        }
        for c in run["calls"]
        for p in c["problems"]
    ]
    errors = [
        {"모델": PROVIDER_LABELS[c["provider"]], "단계": c["stepId"], "오류": c["error"]}
        for c in run["calls"]
        if c["error"]
    ]
    st.markdown(f"**검사에 걸린 문장 {len(problems)}개**")
    if problems:
        st.dataframe(
            sorted(problems, key=lambda p: (p["단계"], p["모델"])),
            hide_index=True,
            column_config={"문장": st.column_config.TextColumn(width="large")},
        )
    if errors:
        st.markdown(f"**호출 오류 {len(errors)}개**")
        st.dataframe(errors, hide_index=True)

with whole:
    st.caption("사용자가 가이드를 처음부터 넘기며 읽는 순서로 한 모델의 결과만 봐요.")
    provider = st.radio(
        "모델",
        providers,
        format_func=lambda p: f"{PROVIDER_LABELS[p]} ({run['models'][p]})",
        horizontal=True,
        key=f"whole:{choice}",
    )
    for step in steps:
        tool = step["inputs"].get("tool")
        st.markdown(f"#### {step['order']}. {step['partLabel']}" + (f"  `{tool}`" if tool else ""))
        st.caption(f"제품: {product_text(step['product'])}")
        render_output(calls.get((provider, step["stepId"])), show_cost=False)
        st.divider()

with prompt_tab:
    prompt_col, prep_col = st.columns(2)
    with prompt_col:
        st.markdown(f"**프롬프트 {run['promptVersion']}** · 세 모델에 똑같이 시스템 지시로 보냄")
        st.code(run["prompt"], language=None, wrap_lines=True)
        with st.expander("응답 형식: 세 모델 모두 이 JSON Schema로만 답하게 강제함"):
            st.json(run["schema"], expanded=False)
    with prep_col:
        st.markdown("**입력 정리: 팁 자리 옮기기**")
        st.caption(
            "근거 시각이 단계 구간을 5초 넘게 벗어난 팁·주의점은 그 시각이 속한 단계로 옮겨요. "
            "옮길 단계에 같은 내용이 있으면 버려요."
        )
        if run["moved"]:
            st.dataframe(
                [
                    {
                        "원래 단계": m["from"],
                        "옮긴 단계": m["to"],
                        "처리": m["action"],
                        "근거 시각": m["at"],
                        "내용": m["value"],
                    }
                    for m in run["moved"]
                ],
                hide_index=True,
            )
        else:
            st.caption("옮긴 것 없음")
        st.markdown("**모델에 보낸 메시지 예시** (첫 단계)")
        st.code(steps[0]["message"], language=None, wrap_lines=True)
