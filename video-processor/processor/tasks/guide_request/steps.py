"""찾은 단계를 AI 서버 요청의 guideInput 단계 형식으로 바꾼다."""

from copy import deepcopy

from processor.schemas.makeup import EYE_MAKEUPS, EYE_ZONES
from processor.tasks.find_steps.product import split_product
from processor.tasks.guide_request.makeup import derive, guide_value, needs_area, union_zone


def normalize_steps(raw_steps: list[dict]) -> list[dict]:
    """판단 근거는 별도 결과에 보관하고 기존 guideInput 계약으로 변환한다."""
    normalized = []
    for step in sorted(raw_steps, key=lambda item: item["absStart"]):
        start, end = step["absStart"], step["absEnd"]
        if start < 0 or end <= start:
            raise ValueError(f"잘못된 단계 시간: {start} ~ {end}")
        step = derive(deepcopy(step))
        explicit = step.get("areaSource") == "explicit"
        tool = step.get("isCosmeticApplication") is False
        area = step.get("area") or step.get("faceArea")
        unresolved = not area or (needs_area(step) and guide_value(step) is None)
        makeup = "other" if unresolved or tool else step.get("makeup") or "other"
        # 합친 단계는 거친 눈 자리를 모두 본다. 위와 아래를 다 거치면 both다.
        eye_zone = (
            union_zone([e.get("faceArea") for e in step.get("events", [])] + [step.get("faceArea")])
            if makeup in EYE_MAKEUPS
            else None
        )
        product = step.get("product") or split_product(step.get("productName"))
        details = list(
            dict.fromkeys(
                event["summary"]
                for event in step.get("events", [])
                if event.get("summary")
            )
        )
        summary = "; ".join(details) if details else step["summary"]
        area_fact_source = step.get("areaFactSource") or (
            "voice" if explicit else "estimated"
        )
        order = len(normalized) + 1
        normalized.append(
            {
                "stepId": f"step_{order:02d}",
                "order": order,
                "startSeconds": start,
                "endSeconds": end,
                "makeup": makeup,
                "partLabel": "부위 미확정" if unresolved and not tool else step["partLabel"],
                "summary": summary,
                "isCosmeticApplication": step["isCosmeticApplication"],
                "product": {**product, "palette": None} if product else None,
                "facts": {
                    "area": {
                        "value": "부위 미확정" if unresolved else area,
                        "source": area_fact_source if not unresolved else "estimated",
                        "at": start if explicit and not unresolved else None,
                    }
                },
            }
            | ({"eyeZone": eye_zone} if eye_zone in EYE_ZONES else {})
            | ({"speech": step["speech"]} if step.get("speech") else {})
        )
    return normalized
