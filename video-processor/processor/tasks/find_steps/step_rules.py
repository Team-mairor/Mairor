"""단계 묶기·붙이기 규칙: 같은 화장품은 한 단계, 브러시로 펴 바르기·바르며 대는 도구는 앞 단계에,
바르는 단계에 붙은 도구 이름은 떼기, 끝은 다음 단계를 넘지 않게, 장 경계는 넘지 않게."""

import re

# 바르는 동안 대고 쓰는 도구. 따로 하는 동작(뷰러·속눈썹 붙이기)과 달리 그 화장품 단계의 일부다.
# '선가드'·'UV 쉴드' 같은 선크림 이름에 걸리지 않게 눈에 대는 것만 본다.
AID_TOOL = re.compile(r"(아이|마스카라|eye|mascara)\s*(가드|쉴드|guard|shield)", re.I)


def name_key(step: dict) -> str:
    return re.sub(r"\s+", "", (step.get("productName") or "").casefold())


def same_name(a: dict, b: dict) -> bool:
    return bool(name_key(a)) and name_key(a) == name_key(b)


def aid_tool(step: dict) -> bool:
    return bool(AID_TOOL.search(step.get("productName") or ""))


def same_product(a: dict, b: dict) -> bool:
    return same_name(a, b) and a["makeup"] == b["makeup"]


def absorb_blending(steps: list[dict]) -> list[dict]:
    """바로 앞 화장품을 같은 자리에서 펴 바르는 도구 단계는 그 화장품 단계에 넣는다.

    정답표는 브러시 블렌딩을 그 제품 단계에 포함해 센다. 모델이 이를 도구 단계로 따로 주면
    AI의 끝 직후 사진이 펴 바르는 도중에 찍힌다. 도구 단계에 제품 이름이 없거나 바로 앞 단계와 같은 제품
    이름이면(그 제품을 펴는 것) 붙인다. 뷰러·속눈썹처럼 자리가 다르거나 다른 이름이 붙은 도구 단계는 둔다.
    장이 다르면 붙이지 않는다.
    """
    return _absorb(steps, lambda prev, step: not step.get("productName") or same_name(prev, step))


def absorb_aid_tools(steps: list[dict]) -> list[dict]:
    """아이가드처럼 바르는 동안 대는 도구 단계는 바로 앞 화장품 단계에 넣는다(RBm4rzufBV0 15:32 언더 마스카라가
    아이가드 단계로 갈라짐).

    absorb_blending과 따로 그 뒤에 돌린다. 함께 돌리면 길어진 화장품 단계에 바로 뒤 이름 없는 도구 단계(핀셋으로
    속눈썹 모으기)가 펴 바르기로 딸려 붙는다.
    """
    return _absorb(steps, lambda prev, step: aid_tool(step))


def _absorb(steps: list[dict], belongs) -> list[dict]:
    """같은 장·같은 자리에서 바로 앞 화장품 단계에 딸린(belongs) 도구 단계를 그 단계에 넣는다."""
    places = lambda s: {e.get("faceArea") for e in s["events"]} - {None}
    out = []
    for step in sorted(steps, key=lambda s: (s["absStart"], s["absEnd"])):
        prev = out[-1] if out else None
        if (prev and prev.get("isCosmeticApplication") and not step.get("isCosmeticApplication")
                and prev.get("chapter") == step.get("chapter") and belongs(prev, step) and places(prev) & places(step)):
            out[-1] = dict(prev, absEnd=max(prev["absEnd"], step["absEnd"]), events=prev["events"] + step["events"])
            continue
        out.append(step)
    return out


def drop_tool_names(steps: list[dict]) -> list[dict]:
    """바르는 단계에 붙은 도구 이름을 떼고, 같은 장에서 앞서 쓴 같은 종류 화장품 이름을 잇는다(없으면 이름 없음).

    자막은 지금 바르는 제품이 아니라 앞으로 쓸 제품을 미리 띄우기도 한다. RBm4rzufBV0 15:21 언더 마스카라는
    바로 앞에 소개한 인조속눈썹 자막이 남아 그 이름을 받았다. 도구 단계에는 화장품 이름이 붙지 않으므로 같은 장
    도구 단계의 이름과 바르며 대는 도구 이름은 화장품이 아니다. 다만 바로 앞 화장품과 이름이 같은 도구 단계는
    그 화장품을 펴는 것이라(자리가 없어 absorb_blending이 못 붙인 것) 세지 않는다.
    """
    ordered = sorted(steps, key=lambda s: (s["absStart"], s["absEnd"]))
    tools = {(step.get("chapter"), name_key(step)) for prev, step in zip([None, *ordered], ordered)
             if not step.get("isCosmeticApplication") and name_key(step)
             and not (prev and prev.get("isCosmeticApplication") and same_name(prev, step))}
    out = []
    for step in ordered:
        if (step.get("isCosmeticApplication") and name_key(step)
                and ((step.get("chapter"), name_key(step)) in tools or aid_tool(step))):
            before = next((s for s in reversed(out) if s.get("isCosmeticApplication") and name_key(s)
                           and s.get("chapter") == step.get("chapter") and s["makeup"] == step["makeup"]), None)
            step = step | {"product": before.get("product") if before else None,
                           "productName": before.get("productName") if before else None,
                           "videoProductName": step["productName"]}
        out.append(step)
    return out


def fit_ends(steps: list[dict]) -> list[dict]:
    """단계 끝이 다음 단계 시작을 넘지 않게 한다. 끝을 초의 끝으로 잡거나(1초) 앞뒤 확인으로 넓히면 겹칠 수 있다."""
    out = [dict(step) for step in sorted(steps, key=lambda s: (s["absStart"], s["absEnd"]))]
    for step, nxt in zip(out, out[1:]):
        if step["absStart"] < nxt["absStart"] < step["absEnd"]:
            step["absEnd"] = nxt["absStart"]
    return out


def keep_inside(steps: list[dict], start: float, end: float) -> list[dict]:
    """조각이 맡은 구간 [start, end]에 절반 넘게 들어오는 단계만 남기고, 밖으로 나간 시작·끝은 자른다.

    조각은 앞 키프레임부터 잘라 앞 구간의 마지막 몇 초가 겹친다. 그곳에서 바르던 앞 장의 단계는 앞 조각이 맡고,
    GMS 시각이 1~2초 어긋나 경계 조금 앞에서 시작한 이 장의 단계는 이 조각에 남는다.
    """
    return [clamp(step, start, end) for step in steps
            if (min(step["absEnd"], end) - max(step["absStart"], start)) * 2 > step["absEnd"] - step["absStart"]]


def assign_chapters(steps: list[dict], chapters: list[dict]) -> list[dict]:
    """단계마다 가장 많이 겹치는 장을 붙이고(chapter, chapterStart, chapterEnd) 그 장 밖으로 나간 시작·끝을 자른다.

    장 경계는 단계가 넘지 않는다. GMS가 장 경계를 몇 초 넘겨 적어도 한 장 안으로 들인다. 장 나눔이 없으면 그대로 둔다.
    """
    out = []
    for step in steps:
        if not chapters:
            out.append(step)
            continue
        chapter = max(chapters, key=lambda c: min(step["absEnd"], c["end"]) - max(step["absStart"], c["start"]))
        out.append(clamp(step, chapter["start"], chapter["end"])
                   | {"chapter": chapter["chapter"], "chapterStart": chapter["start"], "chapterEnd": chapter["end"]})
    return out


def clamp(step: dict, start: float, end: float) -> dict:
    """단계의 시작·끝을 [start, end] 안으로 자르고, 그 안에 닿은 자리(events)만 남긴다(하나도 없으면 그대로)."""
    a, b = max(step["absStart"], start), min(step["absEnd"], end)
    events = [e for e in step["events"] if min(e["absEnd"], b) > max(e["absStart"], a)] or step["events"]
    return step | {"absStart": a, "absEnd": b, "events": events}


def merge_same_product(steps: list[dict]) -> list[dict]:
    """이어지는 같은 화장품(같은 AI 값)은 한 단계다. 다른 화장품을 쓴 뒤 다시 쓰면 따로 두고, 장이 다르면 묶지 않는다."""
    merged = []
    for step in sorted(steps, key=lambda s: (s["absStart"], s["absEnd"])):
        if merged and same_product(merged[-1], step) and merged[-1].get("chapter") == step.get("chapter"):
            last = merged[-1]
            last["absEnd"] = max(last["absEnd"], step["absEnd"])
            last["events"] += step["events"]
            areas = [a for a in dict.fromkeys(e["area"] for e in last["events"]) if a]
            last["area"] = ", ".join(areas)
        else:
            merged.append(dict(step, events=list(step["events"])))
    return merged
