package com.mairor.backend.products.imports;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.products.dto.request.CatalogDryRunRequest;
import com.mairor.backend.products.dto.response.CatalogDryRunResponse;
import com.mairor.backend.products.dto.response.CatalogDryRunResponse.Outcome;
import com.mairor.backend.products.dto.response.CatalogDryRunResponse.Problem;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.imports.CollectedProductReader.ReadResult;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

/**
 * 수집 상품을 DB 에 반영하기 전에 어떻게 판정될지 보여 준다(수집 파일을 적재 전에 검토하는 용도). **아무것도 바꾸지 않는다.** 제품·호수·칸·색, 실행 기록 모두
 * 만들지 않는다.
 *
 * <p>사전 판정이다. 호출 시점의 DB 기준이라 그 사이 다른 적재나 정정이 있으면 실제 적재 결과가 달라질 수 있다.
 *
 * <p>요청은 개수와 배열 여부만 검사하고({@code 400}), 항목은 건마다 읽는다. 한 건이 틀리거나 판정 중 오류가 나도 나머지 건은 계속 판정한다. 실행 기록이
 * 필요한 시작·묶음·종료 입구는 적재 단계(S15P31A306-295)에서 같은 판정 위에 붙는다.
 *
 * <p><b>이 메서드는 트랜잭션을 열지 않는다.</b> 건마다 {@link CatalogMatchPlanner#plan}이 자기 읽기 전용 트랜잭션을 연다. 바깥에 트랜잭션이
 * 하나 있으면 한 건의 판정이 예외로 끝날 때 그 트랜잭션 전체가 롤백 전용으로 표시되어, 예외를 잡아 그 건만 {@code FAILED}로 돌려줘도 마지막에 {@code
 * UnexpectedRollbackException}으로 응답 전체가 500 이 된다. DB 오류라면 뒤의 건들도 중단된 트랜잭션 안에서 실패한다.
 */
@Service
public class CatalogDryRunService {

  public static final int MAX_ITEMS = 100;

  private static final Logger log = LoggerFactory.getLogger(CatalogDryRunService.class);

  private final CatalogMatchPlanner planner;

  public CatalogDryRunService(CatalogMatchPlanner planner) {
    this.planner = planner;
  }

  /**
   * @throws BusinessException 400 {@code VALIDATION_FAILED}: {@code items}가 없거나 배열이 아니거나 비었거나
   *     {@value #MAX_ITEMS}건을 넘으면
   */
  public CatalogDryRunResponse dryRun(CatalogDryRunRequest request) {
    JsonNode items = request == null ? null : request.items();
    if (items == null || !items.isArray()) {
      throw invalid("items 는 배열이어야 합니다.");
    }
    if (items.isEmpty()) {
      throw invalid("items 는 1건 이상이어야 합니다.");
    }
    if (items.size() > MAX_ITEMS) {
      throw invalid("items 는 " + MAX_ITEMS + "건까지입니다.");
    }
    List<CatalogDryRunResponse.Item> results = new ArrayList<>(items.size());
    for (int i = 0; i < items.size(); i++) {
      results.add(judge(i, items.get(i)));
    }
    return new CatalogDryRunResponse(List.copyOf(results));
  }

  private CatalogDryRunResponse.Item judge(int index, JsonNode raw) {
    ReadResult read = CollectedProductReader.read(raw);
    if (!read.isValid()) {
      return new CatalogDryRunResponse.Item(
          index,
          read.itemKey(),
          Outcome.INVALID,
          null,
          List.of(),
          read.issues().stream().map(Problem::from).toList());
    }
    try {
      return fromPlan(index, planner.plan(read.product()));
    } catch (RuntimeException e) {
      // 한 건의 예상 밖 오류가 요청 전체를 500 으로 만들지 않게 그 건만 실패로 돌려준다
      log.warn("수집 상품 판정에 실패했습니다. itemKey={}", read.itemKey(), e);
      return new CatalogDryRunResponse.Item(
          index, read.itemKey(), Outcome.FAILED, null, List.of(), List.of());
    }
  }

  private static CatalogDryRunResponse.Item fromPlan(int index, ImportPlan plan) {
    Outcome outcome =
        switch (plan.outcome()) {
          case NEW -> plan.isPartial() ? Outcome.PARTIAL : Outcome.CREATED;
          case UPDATE -> plan.isPartial() ? Outcome.PARTIAL : Outcome.UPDATED;
          case STALE -> Outcome.STALE;
          case AMBIGUOUS -> Outcome.AMBIGUOUS;
          case UNCLASSIFIED -> Outcome.UNCLASSIFIED;
        };
    Product existing = plan.existing();
    List<ImportReason> reasons =
        plan.allReasons().stream().sorted(Comparator.naturalOrder()).toList();
    return new CatalogDryRunResponse.Item(
        index,
        plan.item().itemKey(),
        outcome,
        existing == null ? null : existing.getId().toString(),
        reasons,
        List.of());
  }

  private static BusinessException invalid(String reason) {
    return new BusinessException(
        ErrorCode.VALIDATION_FAILED.status(),
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError("items", reason)),
        null);
  }
}
