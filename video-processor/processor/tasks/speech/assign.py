"""받아 적은 말을 단계에 붙인다. 설명이 그 단계에서 유튜버가 한 말(요령·주의·양)을 근거로 쓸 수 있게 한다.

- 단계 시간 안의 말은 그 단계에 붙인다.
- 단계 사이의 말은 장 나눔이 있으면 같은 장의 가장 가까운 단계에, 없으면 MAX_GAP초 안의 가장 가까운 단계에 붙인다.
  유튜버는 바르기 전에 제품을 소개하고 바른 뒤에 요령을 덧붙인다(정답표 블러셔: 23:21 "블러셔를 해 주겠습니다",
  24:19 "이렇게 하면 혈색이 싹 통일돼 보이면서"). 거리가 같으면 뒤 단계(다음 제품 소개)에 붙인다.
- 어느 단계에도 붙지 않는 말(인사, 단계 없는 장의 이야기)은 버린다.
"""

MAX_GAP = 15.0


def gap(step: dict, at: float) -> float:
    """말 시각에서 단계 시간까지의 거리(초). 단계 안이면 0이다."""
    if at < step["absStart"]:
        return step["absStart"] - at
    return max(0.0, at - step["absEnd"])


def attach_speech(steps: list[dict], lines: list[dict]) -> list[dict]:
    """단계마다 붙은 말을 speech([{at, text}], 시각 순서)에 담아 돌려준다."""
    out = [dict(step, speech=[]) for step in steps]
    for line in lines:
        at = line["at"]
        inside = [s for s in out if s["absStart"] <= at < s["absEnd"]]
        if inside:
            inside[-1]["speech"].append(line)
            continue
        near = [s for s in out
                if (s.get("chapterStart") is not None and s["chapterStart"] <= at < s["chapterEnd"])
                or (s.get("chapterStart") is None and gap(s, at) <= MAX_GAP)]
        if near:
            min(near, key=lambda s: (gap(s, at), -s["absStart"]))["speech"].append(line)
    return out
