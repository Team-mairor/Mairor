package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.imports.CatalogImportService.ItemResult;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** 건 묶음의 처리 결과. 요청의 항목 순서대로 한 건에 하나씩 온다. */
public record CatalogImportBatchResponse(
    @ArraySchema(arraySchema = @Schema(description = "건별 결과. 요청 항목과 같은 순서")) List<Item> results) {

  public static CatalogImportBatchResponse from(List<ItemResult> results) {
    return new CatalogImportBatchResponse(
        java.util.stream.IntStream.range(0, results.size())
            .mapToObj(i -> Item.from(i, results.get(i)))
            .toList());
  }

  /** 건 하나의 결과. */
  public record Item(
      @Schema(description = "요청 항목의 위치(0부터)", example = "0") int index,
      @Schema(description = "수집기가 붙인 건의 위치. 읽지 못했으면 null", example = "000123", nullable = true)
          String itemKey,
      @Schema(
              description =
                  "NEW·UPDATE 반영함, STALE 오래된 수집이라 반영 안 함, AMBIGUOUS 다른 출처의 같은 제품이 있어 합치지 않음,"
                      + " UNCLASSIFIED 카테고리·종류를 정할 수 없음, INVALID 형식이 틀림, FAILED 처리 중 오류(그 건만 되돌림)")
          ImportItemOutcome outcome,
      @Schema(description = "일부만 반영했거나 기존 값을 지킨 사유가 있는가") boolean partial,
      @ArraySchema(arraySchema = @Schema(description = "사유 코드. 없으면 빈 목록")) List<String> reasons,
      @Schema(description = "반영한 제품의 ID. 반영하지 않았으면 null", nullable = true) String productId,
      @Schema(description = "저장하거나 바꾼 색 칸 수", example = "2") int colorsApplied,
      @Schema(description = "이미 처리한 건이라 저장된 결과를 돌려준 것이면 true. 이때는 아무것도 다시 반영하지 않는다")
          boolean duplicate,
      @Schema(description = "건 기록을 남겼는가. itemKey 를 읽지 못한 건만 false") boolean recorded,
      @Schema(description = "INVALID 의 문제 요약이나 FAILED 의 오류 요약. 아니면 null", nullable = true)
          String message) {

    static Item from(int index, ItemResult result) {
      return new Item(
          index,
          result.itemKey(),
          result.outcome(),
          result.partial(),
          result.reasons(),
          result.productId() == null ? null : result.productId().toString(),
          result.colorsApplied(),
          result.duplicate(),
          result.recorded(),
          result.message());
    }
  }
}
