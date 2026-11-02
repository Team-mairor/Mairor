from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel
from app.schemas.manifest import Makeup

TRIANGLE_COUNT = 898
BARY_TOLERANCE = 0.001
NO_AREA_MAKEUPS: tuple[Makeup, ...] = ("other", "mascara")

RegionName = Literal[
    "leftEye",
    "rightEye",
    "leftBrow",
    "rightBrow",
    "lipsOuter",
    "lipsInner",
    "leftCheek",
    "rightCheek",
    "faceOval",
]

AreaStatus = Literal["extracted", "template", "notApplicable", "failed"]

GuideSetSource = Literal["extracted", "manual"]


class MeshAnchor(CamelModel):
    """얼굴 주소. FE 얼굴 구조 스키마(face/types.ts)의 MeshAnchor와 같다.

    triangle은 shared/face-mesh/triangles.v1.json의 배열 위치(0~897)다.
    bary는 세 꼭짓점에 대한 비율로 합이 1이고, 삼각형 밖이면 음수가 될 수 있다.
    """

    triangle: int = Field(ge=0, lt=TRIANGLE_COUNT)
    bary: tuple[float, float, float]

    @field_validator("bary")
    @classmethod
    def check_bary_sum(cls, bary: tuple[float, float, float]) -> tuple[float, float, float]:
        if abs(sum(bary) - 1) > BARY_TOLERANCE:
            raise ValueError(f"bary 합은 1이어야 합니다 (지금 {sum(bary):g})")
        return bary


class PolygonShape(CamelModel):
    """도포 영역 테두리. outline은 한 바퀴 도는 순서이고 마지막 점은 첫 점으로 이어 닫는다."""

    type: Literal["polygon"]
    outline: list[MeshAnchor] = Field(min_length=3)


class GuideSet(CamelModel):
    """부위별 묶음. region은 얼굴의 어디·어느 쪽인지, exclude는 이 영역에서 뺄 부위다."""

    region: RegionName
    source: GuideSetSource
    guides: list[PolygonShape] = Field(min_length=1)
    exclude: list[RegionName] = Field(default_factory=list)


class AreaSubStep(CamelModel):
    """하위 단계. status에 따라 guideSets · templateId · reasons를 채우는 규칙이 정해져 있다.

    extracted: 영역 1개 이상 / template: 영역 없이 templateId와 이유 / notApplicable: 모두 비움 /
    failed: 영역 없이 이유만
    """

    sub_step_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    status: AreaStatus
    reasons: list[str]
    template_id: Makeup | None
    guide_sets: list[GuideSet]

    @model_validator(mode="after")
    def check_status(self) -> "AreaSubStep":
        status = self.status
        if status == "extracted" and not self.guide_sets:
            raise ValueError("extracted이면 guideSets가 1개 이상이어야 합니다")
        if status != "extracted" and self.guide_sets:
            raise ValueError(f"{status}이면 guideSets가 비어 있어야 합니다")
        if status == "template" and self.template_id in (None, "other"):
            raise ValueError("template이면 templateId에 other가 아닌 화장 종류를 적어야 합니다")
        if status != "template" and self.template_id is not None:
            raise ValueError(f"{status}이면 templateId가 null이어야 합니다")
        if status in ("template", "failed") and not self.reasons:
            raise ValueError(f"{status}이면 reasons가 1개 이상이어야 합니다")
        if status in ("extracted", "notApplicable") and self.reasons:
            raise ValueError(f"{status}이면 reasons가 비어 있어야 합니다")
        return self


class AreaStep(CamelModel):
    """가이드 입력의 단계 하나. stepId · order · makeup은 가이드 입력 그대로다."""

    step_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    makeup: Makeup
    sub_steps: list[AreaSubStep] = Field(min_length=1)

    @model_validator(mode="after")
    def check_sub_steps(self) -> "AreaStep":
        """하위 단계 번호와, 영역이 없는 화장 종류의 상태를 본다.

        makeup이 NO_AREA_MAKEUPS(other, mascara)이면 notApplicable이고, 그 밖에는 쓰지 않는다.
        마스카라는 영역 안내 없이 설명만 하기로 해서 other처럼 영역이 없다.
        """
        for order, sub_step in enumerate(self.sub_steps, start=1):
            if sub_step.order != order:
                raise ValueError(f"{self.step_id}의 subSteps는 order 1부터 차례대로 넣어야 합니다")
            if sub_step.sub_step_id != f"{self.step_id}-{order}":
                raise ValueError(f"subStepId는 {self.step_id}-{order}여야 합니다")
            no_area = self.makeup in NO_AREA_MAKEUPS
            if no_area and sub_step.status != "notApplicable":
                raise ValueError(
                    f"{self.step_id}는 makeup이 {self.makeup}라 notApplicable이어야 합니다"
                )
            if not no_area and sub_step.status == "notApplicable":
                raise ValueError("notApplicable은 makeup이 other나 mascara인 단계에만 씁니다")
        return self


class GuideArea(CamelModel):
    """영상 하나의 단계별 도포 영역. 형식 설명은 shared/guide-area/README.md."""

    video_id: str = Field(min_length=1)
    mesh_version: Literal["v1"]
    steps: list[AreaStep] = Field(min_length=1)

    @field_validator("steps")
    @classmethod
    def check_steps(cls, steps: list[AreaStep]) -> list[AreaStep]:
        orders = [step.order for step in steps]
        if orders != sorted(set(orders)):
            raise ValueError("steps는 order 순서대로, 겹치지 않게 넣어야 합니다")
        if len({step.step_id for step in steps}) != len(steps):
            raise ValueError("stepId가 겹칩니다")
        return steps
