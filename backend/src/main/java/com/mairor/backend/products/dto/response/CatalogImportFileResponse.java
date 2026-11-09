package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.imports.CatalogImportFileService.FileImportResult;
import io.swagger.v3.oas.annotations.media.Schema;

/** 실행 결과 파일 적재 결과. 파일이 크면 끝날 때까지({@code finished=true}) 같은 요청을 반복한다. */
public record CatalogImportFileResponse(
    @Schema(description = "적재 실행의 현재 모습") CatalogImportRunResponse run,
    @Schema(description = "이번 호출에서 새로 처리한 건 수. 이미 처리한 건은 세지 않는다", example = "500") int processed,
    @Schema(description = "읽지 못해 건너뛴 줄 수(중간이 깨진 줄, collected 가 없는 줄). 이번 호출이 훑은 범위", example = "0")
        int unreadable,
    @Schema(
            description = "itemKey 가 없어 기록할 곳이 없는 틀린 줄 수. 처리 건 수와 통계에 들어가지 않으므로 수집기 쪽을 고쳐야 한다",
            example = "0")
        int unrecorded,
    @Schema(description = "파일 끝까지 처리해 실행을 COMPLETED 로 끝냈으면 true. false 면 같은 요청을 다시 보낸다")
        boolean finished,
    @Schema(description = "이 실행의 통계(지금까지)") CatalogImportRunStatsResponse stats) {

  public static CatalogImportFileResponse from(FileImportResult result) {
    return new CatalogImportFileResponse(
        CatalogImportRunResponse.from(result.run()),
        result.processed(),
        result.unreadable(),
        result.unrecorded(),
        result.finished(),
        CatalogImportRunStatsResponse.from(result.stats()));
  }
}
