"""단계 묶기·붙이기 규칙: 같은 화장품은 한 단계, 브러시로 펴 바르기는 앞 단계에, 끝은 다음 단계를 넘지 않게,
장 경계는 넘지 않게."""

import re


def same_name(a: dict, b: dict) -> bool:
    name = lambda s: re.sub(r"\s+", "", (s.get("productName") or "").casefold())
    return bool(name(a)) and name(a) == name(b)


def same_product(a: dict, b: dict) -> bool:
    return same_name(a, b) and a["makeup"] == b["makeup"]


def absorb_blending(steps: list[dict]) -> list[dict]:
    """바로 앞 화장품을 같은 자리에서 펴 바르는 도구 단계는 그 화장품 단계에 넣는다.

    정답표는 브러시 블렌딩을 그 제품 단계에 포함해 센다. 모델이 이를 도구 단계로 따로 주면
    AI의 끝 직후 사진이 펴 바르는 도중에 찍힌다. 도구 단계에 제품 이름이 없거나 바로 앞 단계와 같은 제품
    이름이면(그 제품을 펴는 것) 붙인다. 뷰러·속눈썹처럼 자리가 다르거나 다른 이름이 붙은 도구 단계는 둔다.
    장이 다르면 붙이지 않는다.
    """
    out = []
    for step in sorted(steps, key=lambda s: (s["absStart"], s["absEnd"])):
        prev = out[-1] if out else None
        places = lambda s: {e.get("faceArea") for e in s["events"]} - {None}
        if (prev and prev.get("isCosmeticApplication") and not step.get("isCosmeticApplication")
                and prev.get("chapter") == step.get("chapter")
                and (not step.get("productName") or same_name(prev, step)) and places(prev) & places(step)):
            out[-1] = dict(prev, absEnd=max(prev["absEnd"], step["absEnd"]), events=prev["events"] + step["events"])
            continue
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
