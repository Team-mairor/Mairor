from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import CamelModel

Makeup = Literal[
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


class VideoSource(CamelModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    duration_seconds: float = Field(gt=0)


class Product(CamelModel):
    name: str | None = None
    shade: str | None = None
    product_id: str | None = None


class Step(CamelModel):
    step_id: str
    order: int = Field(ge=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    makeup: Makeup
    product: Product | None = None

    @model_validator(mode="after")
    def check_range(self) -> "Step":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("endSeconds는 startSeconds보다 커야 합니다")
        return self


class Frame(CamelModel):
    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    step_id: str | None
    path: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Manifest(CamelModel):
    video_id: str
    source: VideoSource
    steps: list[Step] = Field(min_length=1)
    frames: list[Frame] = Field(min_length=1)

    @model_validator(mode="after")
    def check_frame_step_ids(self) -> "Manifest":
        step_ids = {step.step_id for step in self.steps}
        for frame in self.frames:
            if frame.step_id is not None and frame.step_id not in step_ids:
                raise ValueError(f"frames의 stepId {frame.step_id}가 steps에 없습니다")
        return self
