from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel
from app.schemas.manifest import Makeup

TRIANGLE_COUNT = 898
BARY_TOLERANCE = 0.001
NO_AREA_MAKEUPS: tuple[Makeup, ...] = ("other",)
CONCEALER_MAKEUPS: tuple[Makeup, ...] = ("foundation", "highlight")
TemplateId = Literal[
    Makeup,
    "eyeshadowUpper",
    "eyeshadowUnder",
    "eyelinerWaterline",
    "eyelinerUnder",
    "blushNose",
    "contourNose",
]

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

GaugeReason = Literal[
    "noArea", "noMaps", "tooFewCells", "colorSpread", "sidesDisagree", "notDarker"
]
GaugeDirection = Literal["darker", "lighter", "same"]
HEX_PATTERN = r"^#[0-9A-Fa-f]{6}$"


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


class ArrowShape(CamelModel):
    """바르는 방향. from은 먼저 바른 곳(시작점), to는 나중에 바른 곳이고 FE가 from → to로 그린다.

    FE 얼굴 구조 스키마(face/types.ts)의 arrow 도형과 같다.
    """

    type: Literal["arrow"]
    start: MeshAnchor = Field(alias="from")
    end: MeshAnchor = Field(alias="to")


class GuideSet(CamelModel):
    """부위별 묶음. region은 얼굴의 어디·어느 쪽인지, exclude는 이 영역에서 뺄 부위다.

    guides에는 도포 영역(polygon)이 1개 이상 있어야 하고, 방향(arrow)은 순서를 알 때만 넣는다.
    """

    region: RegionName
    source: GuideSetSource
    guides: list[PolygonShape | ArrowShape] = Field(min_length=1)
    exclude: list[RegionName] = Field(default_factory=list)

    @field_validator("guides")
    @classmethod
    def check_polygon(
        cls, guides: list[PolygonShape | ArrowShape]
    ) -> list[PolygonShape | ArrowShape]:
        if not any(guide.type == "polygon" for guide in guides):
            raise ValueError("guides에는 polygon이 1개 이상 있어야 합니다")
        return guides


class GaugeColor(CamelModel):
    """색 하나. hex는 sRGB #RRGGBB다.

    lab은 같은 sRGB 색을 D65 흰색 기준 CIELAB으로 바꾼 (L 밝기 0~100, a 초록-빨강, b 파랑-노랑)이다.
    """

    hex: str = Field(pattern=HEX_PATTERN)
    lab: tuple[float, float, float]


class GaugeEffect(CamelModel):
    """화장 효과. 화장이 그 자리 색을 얼마나, 어느 쪽으로 바꿨나다.

    delta는 바른 뒤 색 − 기준 색의 (ΔL, Δa, Δb)다.
    기준 색은 화장이 없었다면 그 자리에 있었을 색으로, 바르기 전 색에서 단계 동안 바뀐 조명을
    덜어 잡는다.
    size는 두 색의 ΔE2000 거리다.
    direction은 밝기가 어두워졌으면 darker(쉐딩·눈썹·아이라인), 밝아졌으면 lighter(하이라이트),
    거의 그대로면 same(색만 바뀜)이다.
    """

    delta: tuple[float, float, float]
    size: float = Field(ge=0)
    direction: GaugeDirection


class GaugeReference(CamelModel):
    """하위 단계의 게이지 기준. 레퍼런스 영상에서 바른 자리의 색과 화장 효과·진하기다.

    값을 냈으면 color·effect·strength가 모두 있고 reason은 null이다.
    못 냈으면 셋 다 null이고 reason에 이유가 든다.
    noArea는 찾은 영역이 없음(기본 가이드 단계), noMaps는 쓸 사진이 없음,
    tooFewCells는 색을 낼 칸이 너무 적음, colorSpread는 사진마다 색이 화장으로 바뀐 양보다
    더 흔들려 화장 색인지 알 수 없음, sidesDisagree는 좌우 짝 부위에서 한쪽은 어두워지고
    다른 쪽은 밝아져 적어도 한쪽이 화장 색이 아님, notDarker는 어두워지는 화장(아이라인·눈썹·쉐딩)이
    어두워지지 않아 찾은 칸이 그린 자리가 아님이다.
    color는 바른 뒤 색이다. 좌우 짝 부위는 찾은 쪽 칸만 합쳐 낸 색이다.
    strength는 effect.size를 0~100으로 바꾼 진하기다.
    white는 레퍼런스 영상의 흰자 색이다. 사용자 캠과 조명 · 카메라를 맞출 때 쓴다.
    눈 화장 전 정면 · 눈 뜬 사진에서 영상마다 한 번 재서 모든 하위 단계에 같은 값을 넣고,
    못 쟀으면 null이다. 값을 못 낸 기준(reason이 있음)에도 null이다.
    """

    color: GaugeColor | None
    effect: GaugeEffect | None
    strength: float | None = Field(ge=0, le=100)
    reason: GaugeReason | None
    white: GaugeColor | None = None

    @model_validator(mode="after")
    def check_reason(self) -> "GaugeReference":
        values = (self.color, self.effect, self.strength)
        if self.reason is None and any(value is None for value in values):
            raise ValueError("reason이 없으면 color·effect·strength가 모두 있어야 합니다")
        if self.reason is not None and any(value is not None for value in values):
            raise ValueError("reason이 있으면 color·effect·strength가 모두 null이어야 합니다")
        if self.reason is not None and self.white is not None:
            raise ValueError("reason이 있으면 white도 null이어야 합니다")
        return self


class AreaSubStep(CamelModel):
    """하위 단계. status에 따라 guideSets · templateId · reasons를 채우는 규칙이 정해져 있다.

    extracted: 영역 1개 이상 / template: 영역 없이 templateId와 이유 / notApplicable: 모두 비움 /
    failed: 영역 없이 이유만
    templateId는 FE 기본 가이드 키다. 화장 종류에 더해 아이섀도는 바른 자리별 키
    (eyeshadowUpper 윗눈두덩, eyeshadowUnder 눈 밑)가 있고, eyeshadow는 위아래 모두다.
    아이라인은 그린 자리별 키(eyelinerWaterline 꼬리 없는 윗점막 선, eyelinerUnder 아랫라인)가 있고,
    eyeliner는 꼬리까지 그린 윗라인이다.
    블러셔는 코(코끝·콧등·콧대)에 바르는 단계의 키 blushNose가 있고, blush는 두 볼이다.
    쉐딩은 콧대 옆에 바르는 단계의 키 contourNose가 있고, contour는 옆광대에서 턱선까지다.
    gauge는 게이지 기준이다. extracted는 값, 또는 영역은 찾았지만 값을 못 낸 이유이고,
    template은 noArea, notApplicable·failed는 null이다.
    게이지 기준을 넣기 전 결과와 색 뽑기가 실패한 결과에는 없다(null).
    """

    sub_step_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    status: AreaStatus
    reasons: list[str]
    template_id: TemplateId | None
    guide_sets: list[GuideSet]
    gauge: GaugeReference | None = None

    @model_validator(mode="after")
    def check_status(self) -> "AreaSubStep":
        status = self.status
        if status == "extracted" and not self.guide_sets:
            raise ValueError("extracted이면 guideSets가 1개 이상이어야 합니다")
        if status != "extracted" and self.guide_sets:
            raise ValueError(f"{status}이면 guideSets가 비어 있어야 합니다")
        if status == "template" and self.template_id in (None, "other"):
            raise ValueError(
                "template이면 templateId에 other가 아닌 기본 가이드 키를 적어야 합니다"
            )
        if status != "template" and self.template_id is not None:
            raise ValueError(f"{status}이면 templateId가 null이어야 합니다")
        if status in ("template", "failed") and not self.reasons:
            raise ValueError(f"{status}이면 reasons가 1개 이상이어야 합니다")
        if status in ("extracted", "notApplicable") and self.reasons:
            raise ValueError(f"{status}이면 reasons가 비어 있어야 합니다")
        self.check_gauge()
        return self

    def check_gauge(self) -> None:
        gauge = self.gauge
        if gauge is None:
            return
        if self.status in ("notApplicable", "failed"):
            raise ValueError(f"{self.status}이면 gauge가 null이어야 합니다")
        if self.status == "template" and gauge.reason != "noArea":
            raise ValueError("template이면 gauge의 reason이 noArea여야 합니다")
        if self.status == "extracted" and gauge.reason == "noArea":
            raise ValueError("extracted이면 gauge의 reason이 noArea일 수 없습니다")


class AreaStep(CamelModel):
    """가이드 입력의 단계 하나. stepId · order · makeup은 가이드 입력 그대로다."""

    step_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    makeup: Makeup
    sub_steps: list[AreaSubStep] = Field(min_length=1)

    @model_validator(mode="after")
    def check_sub_steps(self) -> "AreaStep":
        """하위 단계 번호와, 영역이 없는 화장 종류의 상태를 본다.

        makeup이 NO_AREA_MAKEUPS(other)이면 notApplicable이다.
        그 밖에는 컨실러 단계가 올 수 있는 CONCEALER_MAKEUPS(foundation·highlight)에만 쓴다.
        컨실러는 영역을 띄우지 않기로 해서, 가이드 입력이 foundation·highlight로 보낸 컨실러 단계를
        notApplicable로 적는다.
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
            concealer = self.makeup in CONCEALER_MAKEUPS
            if not no_area and not concealer and sub_step.status == "notApplicable":
                raise ValueError(
                    "notApplicable은 other와 컨실러 단계(foundation·highlight)에만 씁니다"
                )
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
