package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.ImportRunStatus;
import com.mairor.backend.products.imports.CatalogImportRunService.RunView;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

/** 카탈로그 적재 실행의 현재 모습. */
public record CatalogImportRunResponse(
    @Schema(description = "적재 실행의 ID. 건 묶음·하트비트·끝내기 주소에 쓴다") String id,
    @Schema(description = "수집기가 header 에 쓴 runId", example = "5d1f0c2e9a7b4c3e8f6a1b2c3d4e5f60")
        String runId,
    @Schema(
            description =
                "RUNNING 진행 중, COMPLETED 수집기가 끝냄, FAILED 수집기가 실패로 끝냄, ABANDONED 하트비트가 끊겨 서버가 끝냄")
        ImportRunStatus status,
    @Schema(description = "header 의 startedAt", nullable = true) OffsetDateTime startedAt,
    @Schema(description = "서버가 마지막으로 하트비트(건 전송 포함)를 받은 시각") OffsetDateTime lastHeartbeatAt,
    @Schema(description = "끝난 시각. 진행 중이면 null", nullable = true) OffsetDateTime finishedAt,
    @Schema(description = "열기에서만 의미가 있다. 진행 중이던 같은 runId 의 실행을 이어 쓰는 것이면 true") boolean resumed) {

  public static CatalogImportRunResponse from(RunView view) {
    return new CatalogImportRunResponse(
        view.id().toString(),
        view.runId(),
        view.status(),
        view.collectorStartedAt() == null
            ? null
            : view.collectorStartedAt().atOffset(ZoneOffset.UTC),
        view.lastHeartbeatAt().atOffset(ZoneOffset.UTC),
        view.finishedAt() == null ? null : view.finishedAt().atOffset(ZoneOffset.UTC),
        view.resumed());
  }
}
