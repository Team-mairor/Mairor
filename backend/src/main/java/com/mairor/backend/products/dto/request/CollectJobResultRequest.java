package com.mairor.backend.products.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/**
 * 수집 워커가 보내는 작업 결과(CollectJobResult). 계약은 {@code shared/catalog-import/README.md}와 {@code
 * collect_job_result.v1.schema.json}이다.
 */
public record CollectJobResultRequest(
    @Schema(description = "계약 판. 지금 1", example = "1") @NotNull Integer contractVersion,
    @Schema(
            description = "작업 ID. 주소의 jobId 와 같아야 한다",
            example = "5f0c2a1e-8d3b-4c71-9a2e-1b7f3c9d4e10")
        @NotBlank
        String jobId,
    @Schema(
            description =
                "COLLECTED(수집·적재 끝), SEARCH_EMPTY(찾은 상품 없음), UNSUPPORTED_SOURCE(수집할 공식 홈 없음),"
                    + " BLOCKED(봇 차단), FAILED(수집 실패·재시도 소진)",
            example = "COLLECTED")
        @NotNull
        Status status,
    @Schema(description = "COLLECTED 가 아닐 때의 사유 코드", example = "NOT_FOUND", nullable = true)
        @Size(max = 200)
        String reason,
    @Schema(
            description = "COLLECTED 일 때 결과 파일 이름",
            example = "20261112-000012-job-5f0c2a1e.jsonl",
            nullable = true)
        @Size(max = 200)
        String resultFile,
    @Schema(description = "COLLECTED 일 때 결과 파일 header 의 runId", nullable = true) @Size(max = 100)
        String runId,
    @Schema(description = "COLLECTED 일 때 BE 적재 실행 ID", nullable = true) UUID importRunId,
    @Schema(description = "결과 파일에 쓴 상품") @Valid List<Collected> products,
    @Schema(description = "수집하지 못한 상품") @Valid List<Failed> failedProducts,
    @Schema(description = "작업이 끝난 시각", example = "2026-11-12T09:03:10+09:00") @NotNull
        OffsetDateTime finishedAt) {

  /** 워커가 알리는 작업 상태. */
  public enum Status {
    COLLECTED,
    SEARCH_EMPTY,
    UNSUPPORTED_SOURCE,
    BLOCKED,
    FAILED
  }

  public record Collected(
      @Schema(description = "결과 파일 안 줄 위치", example = "000001") @NotBlank @Size(max = 100)
          String itemKey,
      @Schema(description = "출처", example = "OFFICIAL:romand.co.kr") @NotBlank @Size(max = 200)
          String source,
      @Schema(description = "출처의 상품 번호", example = "12") @NotBlank @Size(max = 200)
          String sourceProductId,
      @Schema(
              description = "상품 상세 주소",
              example = "https://romand.co.kr/product/detail.html?product_no=12")
          @NotBlank
          @Size(max = 2000)
          String sourceUrl) {}

  public record Failed(
      @Schema(
              description = "상품 주소",
              example = "https://romand.co.kr/product/detail.html?product_no=13")
          @NotBlank
          @Size(max = 2000)
          String url,
      @Schema(description = "실패 사유 코드", example = "HTTP_ERROR") @NotBlank @Size(max = 100)
          String code) {}

  public List<Collected> productsOrEmpty() {
    return products == null ? List.of() : products;
  }
}
