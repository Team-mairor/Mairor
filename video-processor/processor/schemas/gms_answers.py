"""GMS 답 JSON 모양 (responseSchema)."""

from processor.schemas.makeup import FACE_AREAS, PRODUCT_KINDS

# 영상 속 제품 글자. BE 대조가 브랜드·제품명·호수를 따로 읽어서 따로 묻는다(find_steps/product.py).
PRODUCT = {
    "type": "OBJECT",
    "nullable": True,
    "properties": {field: {"type": "STRING", "nullable": True} for field in ("brand", "name", "shade")},
    "required": ["brand", "name", "shade"],
}


STEP_LIST = {
    "type": "OBJECT",
    "properties": {
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "product": PRODUCT,
                    "productKind": {"type": "STRING", "enum": PRODUCT_KINDS + ["tool"]},
                    "faceArea": {"type": "STRING", "enum": list(FACE_AREAS), "nullable": True},
                    "area": {"type": "STRING"},
                    "partLabel": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "firstTouch": {"type": "STRING"},
                    "lastTouch": {"type": "STRING"},
                    "pieces": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "faceArea": {"type": "STRING", "enum": list(FACE_AREAS), "nullable": True},
                                "firstTouch": {"type": "STRING"},
                                "lastTouch": {"type": "STRING"},
                            },
                            "required": ["faceArea", "firstTouch", "lastTouch"],
                        },
                    },
                },
                "required": [
                    "product", "productKind", "faceArea", "area", "partLabel", "summary",
                    "firstTouch", "lastTouch", "pieces",
                ],
            },
        }
    },
    "required": ["steps"],
}


SPEECH_LINES = {
    "type": "OBJECT",
    "properties": {
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"at": {"type": "STRING"}, "text": {"type": "STRING"}},
                "required": ["at", "text"],
            },
        }
    },
    "required": ["lines"],
}


GAP_FRAMES = {
    "type": "OBJECT",
    "properties": {
        "frames": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "frameId": {"type": "STRING"},
                    "applying": {"type": "BOOLEAN", "nullable": True},
                },
                "required": ["frameId", "applying"],
            },
        }
    },
    "required": ["frames"],
}


def id_items(field: str, value: dict, ids: list[str]) -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "items": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {"imageId": {"type": "STRING", "enum": ids}, field: value},
                    "required": ["imageId", field],
                },
            }
        },
        "required": ["items"],
    }
