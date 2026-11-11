"""부위 이름과 화장품 종류로 AI 서버 값(makeup, eyeZone)을 계산한다.

makeup은 화장품 종류를 따른다. 쿠션·파운데이션·파우더·프라이머·선크림(base)은 foundation,
립밤 같은 스킨케어(skincare)는 other다. 컨실러만 바른 부위로 정한다(미간·콧대·이마·광대 위 highlight,
나머지 foundation). AI 서버는 컨실러 영역을 분석하지 않으므로 컨실러는 분석하는 종류로 보내지 않는다.
눈 위아래(eyeZone)는 아이섀도 기본 그림을 고를 때만 쓰이고, 한 단계가 위와 아래를 다 거치면 both다.
"""

from processor.schemas.makeup import EYE_MAKEUPS, FACE_AREAS, PRODUCT_KINDS


def area_group(event: dict) -> str | None:
    """같은 부위로 보는 이름 묶음. 사전에 없는 이름은 모르는 부위다."""
    entry = FACE_AREAS.get(event.get("faceArea") or "")
    return entry[0] if entry else None


def ai_makeup(kind: str | None, face_area: str | None) -> str | None:
    if kind == "base":
        return "foundation"
    if kind == "skincare":
        return "other"
    if kind == "concealer":
        entry = FACE_AREAS.get(face_area or "")
        return entry[2] if entry else None
    return kind if kind in PRODUCT_KINDS else None


def needs_area(event: dict) -> bool:
    """부위가 있어야 AI 값(makeup)을 정하는 도포. 컨실러만 바른 자리로 makeup이 정해진다."""
    return event.get("isCosmeticApplication") is True and event.get("productKind") == "concealer"


def guide_value(event: dict) -> tuple | None:
    """단계를 더 나누는 기준. AI 서버가 그리는 화장 종류(makeup)이며 모르면 None."""
    makeup = ai_makeup(event.get("productKind"), event.get("faceArea"))
    return None if makeup is None else (makeup,)


def union_zone(face_areas: list[str | None]) -> str | None:
    """한 단계가 거친 눈 자리들의 eyeZone. 위와 아래를 다 거치면 both다. 윗점막은 위로 센다."""
    zones = {FACE_AREAS[a][1] for a in face_areas if a in FACE_AREAS and FACE_AREAS[a][1]}
    if len(zones) <= 1:
        return next(iter(zones), None)
    zones = {"upper" if z == "waterline" else z for z in zones}
    if "both" in zones or {"upper", "under"} <= zones:
        return "both"
    return next(iter(zones))


def derive(event: dict) -> dict:
    """화장품 종류와 부위로 AI 서버 값(makeup, eyeZone)을 다시 계산한다. 직접 고르지 않는다."""
    if event.get("faceArea") not in FACE_AREAS:
        event["faceArea"] = None
    if event.get("productKind") not in PRODUCT_KINDS:
        event["productKind"] = None
    if event.get("isCosmeticApplication") is False:
        event["makeup"] = "other"
        event["eyeZone"] = None
        return event
    event["makeup"] = ai_makeup(event["productKind"], event["faceArea"])
    zone = FACE_AREAS[event["faceArea"]][1] if event["faceArea"] else None
    event["eyeZone"] = zone if event["makeup"] in EYE_MAKEUPS else None
    return event


def area_lines(indent: str = "  ") -> str:
    """지시문에 넣을 부위 목록. 한 줄에 같은 부위 묶음의 이름을 모은다."""
    groups: dict[str, list[str]] = {}
    for name, (group, _zone, _kind) in FACE_AREAS.items():
        groups.setdefault(group, []).append(name)
    return "\n".join(f"{indent}{' / '.join(names)}" for names in groups.values())
