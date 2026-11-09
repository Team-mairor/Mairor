from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import CamelModel

LANDMARK_COUNT = 478

FrameStatus = Literal["ok", "noFace", "rejected", "error"]


class Point(CamelModel):
    """정규화 좌표. 원본 사진 기준, 좌우는 본인 기준. 화면 밖 점은 0~1을 넘는다."""

    x: float
    y: float
    z: float


class ImageSize(CamelModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Pose(CamelModel):
    """라디안. 부호는 FE와 같다.

    본인 기준 왼쪽으로 돌리면 yaw +, 위를 보면 pitch +, 왼쪽으로 기울이면 roll +
    """

    yaw: float
    pitch: float
    roll: float


class Face(CamelModel):
    landmarks: list[Point] = Field(min_length=LANDMARK_COUNT, max_length=LANDMARK_COUNT)
    iod: float = Field(gt=0)
    pose: Pose


class FrameLandmarks(CamelModel):
    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    step_id: str | None
    image_size: ImageSize
    status: FrameStatus
    reasons: list[str] = Field(default_factory=list)
    measures: dict[str, float] = Field(default_factory=dict)
    face_count: int = Field(ge=0)
    face: Face | None

    @model_validator(mode="after")
    def check_face(self) -> "FrameLandmarks":
        if (self.face is None) != (self.face_count == 0):
            raise ValueError("face는 faceCount가 0일 때만 비어 있어야 합니다")
        if self.face is None and self.status not in ("noFace", "error"):
            raise ValueError("얼굴이 없으면 status는 noFace 또는 error여야 합니다")
        if self.face is not None and self.status == "noFace":
            raise ValueError("얼굴이 있으면 status가 noFace일 수 없습니다")
        return self


class LandmarksResult(CamelModel):
    video_id: str
    mesh_version: Literal["v1"] = "v1"
    frames: list[FrameLandmarks]

    @model_validator(mode="after")
    def check_frame_order(self) -> "LandmarksResult":
        indexes = [frame.frame_index for frame in self.frames]
        if indexes != sorted(set(indexes)):
            raise ValueError("frames는 frameIndex 순서대로, 겹치지 않게 넣어야 합니다")
        return self
