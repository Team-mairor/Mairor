"""GMS 답(조각 기준 MM:SS)을 영상 기준 시각의 단계로 바꾼다."""

from processor.tasks.find_steps.clock import parse_clock
from processor.tasks.guide_request.makeup import ai_makeup, derive


def product_name(text: str | None) -> str | None:
    """모델이 빈칸 대신 넣는 'null'·'없음' 같은 글자는 이름이 없는 것으로 본다.

    도구 단계 이름 칸에 종류 이름('tool')을 그대로 쓴 답도 있다(정답표 #23: 아이라인을 펴 바르는 단계가 따로 남아
    끝이 19:35에서 끊김).
    """
    name = (text or "").strip()
    return None if name.casefold() in {"", "null", "none", "n/a", "-", "없음", "모름", "tool", "도구"} else name


def span(item: dict, start: float) -> tuple[float, float]:
    """조각 기준 MM:SS를 영상 기준 초로. 시각이 초 단위라 마지막으로 닿은 초가 끝날 때까지 바른 것으로 본다.

    끝을 그 초의 시작으로 두면 AI의 끝 직후 사진이 마지막 손질 도중에 찍힌다(정답표 #27: 22:05에 끝낸다는 답을
    22:05.0으로 써서 22:05.5까지 바르는 장면이 찍힘).
    """
    first, last = parse_clock(item["firstTouch"]), parse_clock(item["lastTouch"])
    return start + first, start + max(first, last) + 1


def to_steps(rows: list[dict], start: float, index: int) -> list[dict]:
    """조각 답을 영상 기준 시각의 단계로 바꾼다.

    컨실러만 자리별 조각(pieces)으로 다시 나눈다. 바른 자리에 따라 AI 값(makeup)이 달라지기 때문이다
    (미간·콧대 highlight, 코 옆·눈 밑 foundation). 지시만으로는 모델이 한 단계로 뭉쳐 주는 일이 있어
    코드가 나눈다. 다른 화장품은 한 단계로 두고, 조각은 눈 위아래 판단과 설명 글에 쓴다.
    """
    steps = []
    for row in rows:
        tool = row["productKind"] == "tool"
        first, last = span(row, start)
        pieces = []
        for piece in row.get("pieces") or []:
            a, b = span(piece, start)
            pieces.append({"absStart": a, "absEnd": b, "faceArea": piece.get("faceArea"),
                           "area": piece.get("faceArea"), "summary": row["summary"]})
        pieces.sort(key=lambda p: p["absStart"])
        if not pieces:
            pieces = [{"absStart": first, "absEnd": last, "faceArea": row.get("faceArea"),
                       "area": row.get("area") or row.get("faceArea"), "summary": row["summary"]}]
        base = {
            "productName": product_name(row.get("product")),
            "productType": None,
            "productKind": None if tool else row["productKind"],
            "areaSource": "explicit",
            "areaFactSource": "scene",
            "isCosmeticApplication": not tool,
            "isActualUse": True,
            "action": row["summary"],
            "actionKind": "other" if tool else "apply",
            "partLabel": row["partLabel"],
            "summary": row["summary"],
            "clip": index,
        }
        if row["productKind"] == "concealer":
            groups = []
            for piece in pieces:
                makeup = ai_makeup("concealer", piece["faceArea"])
                if groups and (makeup is None or makeup == groups[-1][0]):
                    groups[-1][1].append(piece)
                else:
                    groups.append((makeup, [piece]))
            for _, group in groups:
                areas = [a for a in dict.fromkeys(p["area"] for p in group) if a]
                steps.append(derive(base | {
                    "absStart": min(p["absStart"] for p in group),
                    "absEnd": max(p["absEnd"] for p in group),
                    "faceArea": next((p["faceArea"] for p in group if p["faceArea"]), None),
                    "area": ", ".join(areas) or row.get("area"),
                    "events": group,
                }))
            continue
        steps.append(derive(base | {
            "absStart": min(first, pieces[0]["absStart"]),
            "absEnd": max(last, pieces[-1]["absEnd"]),
            "faceArea": row.get("faceArea"),
            "area": row.get("area") or row.get("faceArea"),
            "events": pieces,
        }))
    return steps
