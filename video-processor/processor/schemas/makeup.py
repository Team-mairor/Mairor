"""화장품 종류·바른 부위 사전과 AI 서버 makeup 값.

모델은 화장품 종류(productKind)와 부위 이름(faceArea)만 고르고, AI 값(makeup, eyeZone)은
tasks/guide_request/makeup.py가 이 사전으로 계산한다. 부위를 더하거나 고칠 때는 FACE_AREAS만 바꾼다.
"""


EYE_MAKEUPS = {"eyeshadow", "eyeliner"}
EYE_ZONES = ["upper", "under", "both", "waterline"]
PRODUCT_KINDS = [
    "eyeshadow",
    "eyeliner",
    "mascara",
    "brow",
    "blush",
    "lip",
    "highlight",
    "contour",
    "base",
    "concealer",
    "skincare",
]


# 부위 이름: (부위 묶음, eyeZone, 컨실러를 바르면 쓰는 makeup)
FACE_AREAS: dict[str, tuple[str, str | None, str]] = {
    "얼굴 전체": ("얼굴 전체", None, "foundation"),
    "이마": ("이마", None, "highlight"),
    "헤어라인": ("헤어라인", None, "foundation"),
    "미간": ("미간", None, "highlight"),
    "콧대": ("콧대", None, "highlight"),
    "코 옆": ("코 옆", None, "foundation"),
    "볼": ("볼", None, "foundation"),
    "광대 위": ("광대 위", None, "highlight"),
    "옆광대~턱선": ("옆광대~턱선", None, "foundation"),
    "턱": ("턱", None, "foundation"),
    "입가": ("입가", None, "foundation"),
    "입술": ("입술", None, "foundation"),
    "눈썹": ("눈썹", None, "foundation"),
    "윗눈두덩": ("눈두덩", "upper", "foundation"),
    "쌍꺼풀 라인": ("눈두덩", "upper", "foundation"),
    # 눈꼬리·눈 앞머리는 위아래를 가르지 않아 eyeZone이 없다. 같이 거친 자리가 있으면 그 자리를 따른다
    "눈꼬리": ("눈꼬리", None, "foundation"),
    "눈 앞머리": ("눈 앞머리", None, "foundation"),
    "눈 밑": ("눈 밑", "under", "foundation"),
    "애교살": ("눈 밑", "under", "foundation"),
    "윗눈두덩과 눈 밑": ("눈두덩과 눈 밑", "both", "foundation"),
    "윗라인": ("윗라인", "upper", "foundation"),
    "윗속눈썹 뿌리": ("윗라인", "upper", "foundation"),
    "위로 뺀 눈꼬리 라인": ("윗라인", "upper", "foundation"),
    "아랫라인": ("아랫라인", "under", "foundation"),
    "아랫속눈썹 뿌리": ("아랫라인", "under", "foundation"),
    "눈꼬리 트임": ("아랫라인", "under", "foundation"),
    "아랫점막": ("아랫라인", "under", "foundation"),
    "윗점막": ("윗점막", "waterline", "foundation"),
    "윗라인과 아랫라인": ("윗라인과 아랫라인", "both", "foundation"),
    "윗속눈썹": ("속눈썹", None, "foundation"),
    "아랫속눈썹": ("속눈썹", None, "foundation"),
}


# AI 서버 makeup 값
MAKEUPS = [
    "foundation",
    "eyeshadow",
    "eyeliner",
    "blush",
    "lip",
    "brow",
    "mascara",
    "contour",
    "highlight",
    "other",
]


# 화장품 종류를 GMS 질문에 쓸 영어 이름
KIND_WORDS = {
    "eyeshadow": "eyeshadow",
    "eyeliner": "eyeliner",
    "mascara": "mascara",
    "brow": "brow product",
    "blush": "blush",
    "lip": "lip product",
    "highlight": "highlighter",
    "contour": "contour (shading) product",
    "base": "base product (cushion, foundation, powder or primer)",
    "concealer": "concealer",
    "skincare": "skincare product (lip balm, moisturizer or toner)",
}
