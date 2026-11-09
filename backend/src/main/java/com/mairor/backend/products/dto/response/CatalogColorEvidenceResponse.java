package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.imports.CatalogEvidenceService.Evidence;
import io.swagger.v3.oas.annotations.media.Schema;
import tools.jackson.databind.JsonNode;

/**
 * 색 칸의 현재 값이 어떤 근거에서 나왔는지. 근거(이미지 URL, 영역, 방법, 품질 점수)는 DB 가 아니라 실행 결과 파일에 있어서, 파일이 보관 기간(30일)이 지나
 * 없으면 {@code fileAvailable=false}이고 {@code evidence}는 비어 있다.
 */
public record CatalogColorEvidenceResponse(
    @Schema(description = "색 칸의 ID(colorId)") String colorId,
    @Schema(description = "칸이 가리키는 근거 키", example = "example-curl-fix-mascara/01-black/1")
        String evidenceKey,
    @Schema(description = "현재 값을 만든 적재 건의 itemKey", example = "000003") String itemKey,
    @Schema(description = "그 건이 속한 실행의 runId") String runId,
    @Schema(
            description = "실행 결과 파일 상대 이름",
            nullable = true,
            example = "20261108-213000-etude.jsonl")
        String resultFile,
    @Schema(description = "실행 결과 파일을 열 수 있었는가. 보관 기간이 지나 지워졌으면 false") boolean fileAvailable,
    @Schema(
            description =
                "그 칸의 근거 기록(imageUrl, imageHash, imageKind, bbox, method, scores 등). 없으면 null",
            nullable = true)
        JsonNode evidence) {

  public static CatalogColorEvidenceResponse from(Evidence found) {
    return new CatalogColorEvidenceResponse(
        found.colorId().toString(),
        found.evidenceKey(),
        found.itemKey(),
        found.runId(),
        found.resultFile(),
        found.fileAvailable(),
        found.evidence());
  }
}
