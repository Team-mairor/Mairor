"""조각 기준 MM:SS 시각과 초 사이 바꾸기."""


def clock(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def parse_clock(text: str) -> float:
    parts = [float(p) for p in text.strip().split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"MM:SS가 아님: {text}")
