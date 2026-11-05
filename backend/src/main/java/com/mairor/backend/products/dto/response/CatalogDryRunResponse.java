package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.imports.ImportIssue;
import com.mairor.backend.products.imports.ImportReason;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** 수집 상품 판정 시험 결과. 요청의 항목 순서대로 한 건에 하나씩 온다. */
public record CatalogDryRunResponse(
    @ArraySchema(arraySchema = @Schema(description = "건별 결과. 요청 항목과 같은 순서")) List<Item> results) {

  /**
   * 건 하나의 결과.
   *
   * <p>사전 판정이다. 호출 시점의 DB 기준이라 그 사이 다른 적재나 정정이 있으면 실제 적재 결과가 달라질 수 있다. 아무것도 저장하지 않는다.
   */
  public record Item(
      @Schema(description = "요청 항목의 위치(0부터)", example = "0") int index,
      @Schema(description = "수집기가 붙인 건의 위치. 읽지 못했으면 null", example = "000123", nullable = true)
          String itemKey,
      @Schema(description = "판정 결과") Outcome outcome,
      @Schema(
              description = "이미 있는 제품의 ID. 새 제품·분류 불가·검사 실패면 null. 모호함(AMBIGUOUS)이면 같은 키를 가진 제품",
              nullable = true)
          String productId,
      @ArraySchema(arraySchema = @Schema(description = "일부만 반영하거나 기존 값을 지킨 사유. 반영에 문제가 없으면 빈 목록"))
          List<ImportReason> reasons,
      @ArraySchema(arraySchema = @Schema(description = "검사 실패(INVALID)의 문제 목록. 아니면 빈 목록"))
          List<Problem> issues) {}

  /** 건의 판정. */
  public enum Outcome {
    /** 새 제품으로 만들 수 있다. */
    CREATED,
    /** 기존 제품을 갱신할 수 있다. */
    UPDATED,
    /** 반영할 수 있지만 일부는 반영하지 않거나 기존 값을 지킨다(reasons 참고). */
    PARTIAL,
    /** 기존 제품이 더 최근에 수집됐다. 반영하지 않는다. */
    STALE,
    /** 다른 출처의 같은 제품 후보가 있다. 자동으로 합치지 않는다. */
    AMBIGUOUS,
    /** 카테고리·종류를 정할 수 없다. */
    UNCLASSIFIED,
    /** 형식이나 계약 규칙에 맞지 않는다(issues 참고). */
    INVALID,
    /** 판정 중 예상하지 못한 오류가 났다. 그 건만 실패하고 나머지는 판정한다. */
    FAILED
  }

  /** 검사 실패의 문제 하나. */
  public record Problem(
      @Schema(description = "문제가 있는 위치", example = "shades[0].colors[0].hex") String path,
      @Schema(description = "문제 종류", example = "INVALID_FORMAT") ImportIssue.Code code,
      @Schema(description = "설명", example = "#RRGGBB 대문자여야 한다") String message) {

    public static Problem from(ImportIssue issue) {
      return new Problem(issue.path(), issue.code(), issue.message());
    }
  }
}
