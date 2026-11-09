package com.mairor.backend.products.dto.request;

import com.mairor.backend.products.entity.CatalogImportRun;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.OffsetDateTime;

/** 카탈로그 적재 실행 열기. 값은 수집기가 실행 결과 파일 header 에 쓴 것과 같다. */
public record CatalogImportStartRequest(
    @Schema(
            description = "수집기가 실행 결과 파일 header 에 쓴 runId. 같은 값으로 다시 열면 진행 중인 실행을 이어 쓴다",
            example = "5d1f0c2e9a7b4c3e8f6a1b2c3d4e5f60")
        @NotBlank
        @Size(max = CatalogImportRun.RUN_ID_MAX_LENGTH)
        String runId,
    @Schema(
            description = "header 의 seed(수집 대상 출처)",
            example = "OFFICIAL:etude.com",
            nullable = true)
        @Size(max = CatalogImportRun.SEED_MAX_LENGTH)
        String seed,
    @Schema(description = "수집기 버전", example = "0.1.0", nullable = true)
        @Size(max = CatalogImportRun.COLLECTOR_VERSION_MAX_LENGTH)
        String collectorVersion,
    @Schema(
            description = "header 의 startedAt. 시간대가 있는 시각",
            example = "2026-11-08T21:30:00+09:00",
            nullable = true)
        OffsetDateTime startedAt,
    @Schema(
            description = "공유 볼륨(/data/catalog-runs)의 실행 결과 파일 상대 이름. 경로 구분자는 쓸 수 없다",
            example = "20261108-213000-etude.jsonl",
            nullable = true)
        @Size(max = CatalogImportRun.RESULT_FILE_MAX_LENGTH)
        @Pattern(
            regexp = "^[A-Za-z0-9][A-Za-z0-9._-]*$",
            message = "파일 이름은 영문·숫자·._- 만 쓰고 경로 구분자를 포함할 수 없다")
        String resultFile) {}
