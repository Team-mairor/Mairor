package com.mairor.backend.analysis.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;

/** 노트북 실패 알림 본문. */
public record ProcessorFailRequest(
    @Schema(
            description =
                "실패 코드. DOWNLOAD_REJECTED · VIDEO_UNAVAILABLE · STEP_EXTRACTION_FAILED · FRAME_EXTRACTION_FAILED"
                    + " · UPLOAD_FAILED · SCHEMA_INVALID, 그 밖의 값도 받는다",
            example = "DOWNLOAD_REJECTED")
        String code,
    @Schema(description = "다시 해 볼 만한지. BE 가 아는 코드면 BE 표를 따르고, 모르는 코드일 때만 쓴다", example = "false")
        Boolean retryable,
    @Schema(description = "원인 설명(운영자가 본다)", example = "YouTube 가 다운로드를 거절했습니다(HTTP 403).")
        String message) {}
