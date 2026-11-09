package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.imports.CatalogImportStatsService.Problem;
import com.mairor.backend.products.imports.CatalogImportStatsService.RunStats;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.Map;

/**
 * 적재 실행 한 번의 통계. 실행이 끝까지 보내졌다(COMPLETED)는 것과 건이 모두 반영됐다는 것은 다르다. 틀린 건과 실패한 건은 실행 상태와 상관없이 여기에 그대로
 * 나온다.
 */
public record CatalogImportRunStatsResponse(
    @Schema(description = "실행의 현재 모습") CatalogImportRunResponse run,
    @Schema(description = "받아서 기록한 건 수", example = "120") int total,
    @Schema(
            description =
                "처리 결과별 건수. NEW·UPDATE 반영, STALE 오래된 수집, AMBIGUOUS 다른 출처의 같은 제품, UNCLASSIFIED 분류 불가,"
                    + " INVALID 형식 틀림, FAILED 처리 중 오류. 없는 결과도 0으로 나온다")
        Map<ImportItemOutcome, Integer> byOutcome,
    @Schema(description = "새 제품으로 반영한 건(NEW)", example = "80") int created,
    @Schema(description = "기존 제품을 갱신한 건(UPDATE)", example = "30") int updated,
    @Schema(description = "반영하지 않은 건(STALE·AMBIGUOUS·UNCLASSIFIED)", example = "6") int skipped,
    @Schema(description = "틀리거나 처리 중 오류가 난 건(INVALID·FAILED)", example = "4") int failed,
    @Schema(description = "일부만 반영했거나 기존 값을 지킨 사유가 있는 건", example = "9") int partial,
    @Schema(description = "저장하거나 바꾼 색 칸 수의 합", example = "212") long colorsApplied,
    @Schema(description = "사유 코드별 건수. 많은 순") Map<String, Integer> reasons,
    @ArraySchema(arraySchema = @Schema(description = "문제가 난 건의 앞부분(itemKey 순, 최대 20건)"))
        List<ProblemItem> problems,
    @Schema(description = "문제가 난 건의 전체 수. problems 가 잘렸는지 알 수 있다", example = "4")
        int problemCount) {

  public static CatalogImportRunStatsResponse from(RunStats stats) {
    return new CatalogImportRunStatsResponse(
        CatalogImportRunResponse.from(stats.run()),
        stats.total(),
        stats.byOutcome(),
        stats.created(),
        stats.updated(),
        stats.skipped(),
        stats.failed(),
        stats.partial(),
        stats.colorsApplied(),
        stats.reasons(),
        stats.problems().stream().map(ProblemItem::from).toList(),
        stats.problemCount());
  }

  /** 문제가 난 건 하나. */
  public record ProblemItem(
      @Schema(description = "수집기가 붙인 건의 위치", example = "000123") String itemKey,
      @Schema(description = "INVALID 또는 FAILED") ImportItemOutcome outcome,
      @ArraySchema(arraySchema = @Schema(description = "사유 코드")) List<String> reasons,
      @Schema(description = "문제 요약", nullable = true) String message) {

    static ProblemItem from(Problem problem) {
      return new ProblemItem(
          problem.itemKey(), problem.outcome(), problem.reasons(), problem.message());
    }
  }
}
