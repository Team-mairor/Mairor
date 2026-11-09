package com.mairor.backend.products.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.UUID;

/** 실행 결과 파일을 읽어 적재하는 요청. */
public record CatalogImportFileRequest(
    @Schema(
            description = "공유 볼륨(/data/catalog-runs)의 실행 결과 파일 상대 이름. 경로 구분자는 쓸 수 없다",
            example = "20261108-213000-etude.jsonl")
        @NotBlank
        @Size(max = 200)
        @Pattern(
            regexp = "^[A-Za-z0-9][A-Za-z0-9._-]*\\.jsonl$",
            message = "파일 이름은 영문·숫자·._- 로 이루어진 .jsonl 이어야 하며 경로를 포함할 수 없다")
        String resultFile,
    @Schema(
            description = "이번 호출에서 새로 처리할 최대 건 수(1~2000). 없으면 500. 파일이 크면 끝날 때까지 같은 요청을 반복한다",
            example = "500",
            nullable = true)
        @Min(1)
        @Max(2000)
        Integer limit,
    @Schema(
            description =
                "다시 처리할 이전 실행의 id. 주면 그 실행에서 FAILED·INVALID 로 끝난 건만 같은 파일에서 다시 읽어 새 실행(<이전 runId>-retry)으로 처리한다",
            nullable = true)
        UUID retryOf) {}
