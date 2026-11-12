"""처리 중 난 오류를 BE 실패 코드로 나눈다 (계약: docs/references/processor-api.md 'fail 코드').

재시도 여부는 BE 표가 정하고, 표에 없는 코드(DOWNLOAD_FAILED · PROCESSOR_ERROR 등)만 retryable을 따른다.
"""

import re
from typing import NamedTuple

import jsonschema
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError
from yt_dlp.utils import DownloadError

from processor.tasks.frames.extract import FrameExtractionError

# BE가 [code]를 앞에 붙여 500자까지 남긴다
MESSAGE_LIMIT = 450
ANSI_COLOR = re.compile(r"\x1b\[[0-9;]*m")
UNAVAILABLE_MARKS = (
    "video unavailable", "private video", "has been removed", "this video is not available", "members-only",
    "confirm your age", "has been terminated", "does not exist",
)
REJECTED_MARKS = ("not a bot", "sign in to confirm", "http error 403", "http error 429", "too many requests")


class Failure(NamedTuple):
    code: str
    retryable: bool
    message: str


def describe_failure(error, stage):
    """오류 종류를 먼저 보고, 종류로 알 수 없으면 오류가 난 단계(stage)로 나눈다."""
    if isinstance(error, DownloadError):
        text = describe(error).lower()
        if any(mark in text for mark in UNAVAILABLE_MARKS):
            return failure("VIDEO_UNAVAILABLE", False, error)
        if any(mark in text for mark in REJECTED_MARKS):
            return failure("DOWNLOAD_REJECTED", False, error)
        return failure("DOWNLOAD_FAILED", True, error)
    if isinstance(error, FrameExtractionError):
        return failure("FRAME_EXTRACTION_FAILED", False, error)
    if isinstance(error, (BotoCoreError, ClientError, S3UploadFailedError)):
        return failure("UPLOAD_FAILED", True, error)
    if isinstance(error, jsonschema.ValidationError):
        return failure("SCHEMA_INVALID", False, error)
    if stage == "EXTRACTING_STEPS":
        return failure("STEP_EXTRACTION_FAILED", True, error)
    if stage == "SEGMENTING":
        return failure("FRAME_EXTRACTION_FAILED", False, error)
    return failure("PROCESSOR_ERROR", True, error)


def failure(code, retryable, error):
    return Failure(code, retryable, f"{type(error).__name__}: {describe(error)}"[:MESSAGE_LIMIT])


def describe(error):
    if isinstance(error, jsonschema.ValidationError):
        where = "/".join(str(p) for p in error.absolute_path) or "(맨 위)"
        return f"{error.message} (위치 {where})"
    return ANSI_COLOR.sub("", str(error)).strip()
