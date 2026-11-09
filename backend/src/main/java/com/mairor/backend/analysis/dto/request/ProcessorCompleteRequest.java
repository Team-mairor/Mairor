package com.mairor.backend.analysis.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;

/** 노트북 완료 알림 본문. */
public record ProcessorCompleteRequest(
    @Schema(
            description =
                "노트북이 올린 AI 요청 JSON(guide_job_request.v2)의 저장소 키. claim 의 s3Prefix 아래여야 한다",
            example =
                "videos/VxAXD6PP76I/jobs/2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f/guide_job_request.json")
        String guideJobRequestKey) {}
