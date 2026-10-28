from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from pydantic import ValidationError

from app.core.errors import AppError
from app.schemas.common import ErrorDetail
from app.schemas.manifest import Frame, Manifest

MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True)
class ReferenceInput:
    folder: Path
    manifest: Manifest

    def frame_path(self, frame: Frame) -> Path:
        return self.folder / frame.path


def load_reference_input(folder: str | Path) -> ReferenceInput:
    folder = Path(folder)
    manifest_path = folder / MANIFEST_FILE
    if not manifest_path.is_file():
        raise AppError(400, "MANIFEST_NOT_FOUND", f"{manifest_path}가 없습니다.")

    try:
        manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except ValidationError as e:
        details = [
            ErrorDetail(field=".".join(str(p) for p in err["loc"]), reason=err["msg"])
            for err in e.errors()
        ]
        raise AppError(
            400, "INVALID_MANIFEST", "manifest.json이 입력 규격과 다릅니다.", details
        ) from e

    reference = ReferenceInput(folder, manifest)
    missing = [frame.path for frame in manifest.frames if not reference.frame_path(frame).is_file()]
    if missing:
        details = [ErrorDetail(field="frames.path", reason=path) for path in missing]
        raise AppError(400, "FRAME_NOT_FOUND", "사진 파일이 없습니다.", details)
    return reference


def read_frame_rgb(reference: ReferenceInput, frame: Frame) -> np.ndarray:
    with Image.open(reference.frame_path(frame)) as image:
        return photo_to_rgb(image, frame)


def photo_to_rgb(image: Image.Image, frame: Frame) -> np.ndarray:
    upright = ImageOps.exif_transpose(image)
    rgb = np.asarray(upright.convert("RGB"))

    if rgb.shape[:2] != (frame.height, frame.width):
        reason = f"manifest {frame.width}x{frame.height}, 실제 {rgb.shape[1]}x{rgb.shape[0]}"
        raise AppError(
            400,
            "FRAME_SIZE_MISMATCH",
            f"{frame.path} 크기가 manifest와 다릅니다.",
            [ErrorDetail(field="frames.width/height", reason=reason)],
        )
    return rgb
