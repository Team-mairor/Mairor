package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.CatalogImportItem;
import com.mairor.backend.products.entity.CatalogImportRun;
import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.event.CatalogColorChanged;
import com.mairor.backend.products.imports.CatalogImportApplier.Applied;
import com.mairor.backend.products.imports.CollectedProductReader.ReadResult;
import com.mairor.backend.products.repository.CatalogImportItemRepository;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import jakarta.persistence.EntityManager;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.JsonNode;

/**
 * 수집 상품 한 건을 읽고 판정해서 카탈로그에 반영하고 결과를 기록한다. **건마다 자기 트랜잭션**이다.
 *
 * <p>한 건의 처리 순서(한 트랜잭션): 같은 출처 제품 잠금 → 건 행을 먼저 저장 → 판정 → 반영 → 결과 확정 → 서비스에 보이는 색이 바뀌었으면 {@link
 * CatalogColorChanged} 발행.
 *
 * <ul>
 *   <li><b>같은 건의 재전송</b>은 한 번만 처리한다. {@code (실행, itemKey)}가 유니크라서, 이미 처리된 건은 저장된 결과를 그대로 돌려주고 반영하지
 *       않는다. 같은 건이 동시에 들어와도 건 행을 먼저 저장하므로 하나만 반영되고 나머지는 저장된 결과를 받는다.
 *   <li><b>같은 제품의 다른 건</b>은 같은 출처·상품 번호를 키로 잠가서 순서대로 처리한다. 아직 없는 새 제품도 잠글 수 있도록 행 잠금이 아니라 트랜잭션 단위
 *       advisory lock 을 쓴다.
 *   <li><b>실패는 그 건만</b> 롤백한다. 제품·호수·칸 변경이 모두 되돌려지고, 실패 기록은 별도 트랜잭션으로 남긴다. 한 건의 오류가 다음 건에 번지지 않는다.
 *   <li>형식이 틀린 건은 판정하지 않고 {@code INVALID} 로 기록한다. {@code itemKey}를 읽지 못한 건은 기록할 곳이 없어 기록하지 않고 알린다.
 * </ul>
 *
 * 끝난 실행에는 건을 더할 수 없고({@link CatalogImportRunClosedException}), 없는 실행도 거절한다({@link
 * CatalogImportRunNotFoundException}). 이 둘은 건의 실패가 아니라 호출의 오류라서 그대로 던진다.
 */
@Service
public class CatalogImportService {

  private static final Logger log = LoggerFactory.getLogger(CatalogImportService.class);
  private static final int MAX_ISSUES_IN_MESSAGE = 3;
  private static final String PROCESSING = "처리 중";

  private final CatalogImportRunRepository runs;
  private final CatalogImportItemRepository items;
  private final CatalogMatchPlanner planner;
  private final CatalogImportApplier applier;
  private final JdbcTemplate jdbc;
  private final EntityManager em;
  private final ApplicationEventPublisher events;
  private final CatalogRunLock runLock;
  private final TransactionTemplate inNewTransaction;

  public CatalogImportService(
      CatalogImportRunRepository runs,
      CatalogImportItemRepository items,
      CatalogMatchPlanner planner,
      CatalogImportApplier applier,
      JdbcTemplate jdbc,
      EntityManager em,
      ApplicationEventPublisher events,
      CatalogRunLock runLock,
      PlatformTransactionManager transactionManager) {
    this.runs = runs;
    this.items = items;
    this.planner = planner;
    this.applier = applier;
    this.jdbc = jdbc;
    this.em = em;
    this.events = events;
    this.runLock = runLock;
    this.inNewTransaction = new TransactionTemplate(transactionManager);
    this.inNewTransaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
  }

  /**
   * 건의 처리 결과.
   *
   * @param itemKey 건의 위치. 읽지 못했으면 {@code null}
   * @param outcome 처리 결과
   * @param partial 일부만 반영했거나 기존 값을 지킨 사유가 있는가
   * @param reasons 사유 코드
   * @param productId 반영한 제품. 반영하지 않았으면 {@code null}
   * @param colorsApplied 저장하거나 바꾼 색 칸 수
   * @param duplicate 이미 처리된 건이라 저장된 결과를 돌려준 것인가
   * @param recorded 건 행을 남겼는가. {@code itemKey}를 읽지 못한 건만 {@code false}
   * @param message 틀린 건({@code INVALID})의 문제 요약이나 실패한 건({@code FAILED})의 오류 요약. 아니면 {@code null}
   * @param changedShadeIds 이번 처리로 서비스에 보이는 색이 바뀐 호수. 재전송으로 돌려준 결과는 비어 있다
   */
  public record ItemResult(
      String itemKey,
      ImportItemOutcome outcome,
      boolean partial,
      List<String> reasons,
      UUID productId,
      int colorsApplied,
      boolean duplicate,
      boolean recorded,
      String message,
      List<UUID> changedShadeIds) {}

  /**
   * 건 하나를 처리한다.
   *
   * @param runId 적재 실행의 id
   * @throws CatalogImportRunNotFoundException 실행이 없으면
   * @throws CatalogImportRunClosedException 실행이 이미 끝났으면
   */
  public ItemResult importItem(UUID runId, JsonNode raw) {
    ReadResult read = CollectedProductReader.read(raw);
    if (read.itemKey() == null) {
      return new ItemResult(
          null,
          ImportItemOutcome.INVALID,
          false,
          issueCodes(read),
          null,
          0,
          false,
          false,
          issueMessage(read),
          List.of());
    }
    Optional<ItemResult> done = existing(runId, read.itemKey());
    if (done.isPresent()) {
      return done.get();
    }
    try {
      return inNewTransaction.execute(status -> process(runId, read));
    } catch (DuplicateItemException e) {
      return existing(runId, read.itemKey()).orElseThrow(() -> e);
    } catch (CatalogImportRunNotFoundException | CatalogImportRunClosedException e) {
      throw e;
    } catch (RuntimeException e) {
      log.warn("수집 상품 적재에 실패했습니다. runId={}, itemKey={}", runId, read.itemKey(), e);
      return recordFailure(runId, read, e);
    }
  }

  private ItemResult process(UUID runId, ReadResult read) {
    // 실행을 끝내는 쪽과 겹치지 않게 공유 잠금을 먼저 잡고, 그 뒤에 실행 상태를 읽는다
    runLock.shared(runId);
    CatalogImportRun run =
        runs.findById(runId).orElseThrow(() -> new CatalogImportRunNotFoundException(runId));
    if (run.getStatus().isFinished()) {
      throw new CatalogImportRunClosedException(run.getRunId(), run.getStatus());
    }
    if (!read.isValid()) {
      CatalogImportItem item = firstSave(run, read.itemKey(), null, null);
      item.recordResult(
          ImportItemOutcome.INVALID, false, issueCodes(read), null, 0, issueMessage(read));
      em.flush();
      return result(item, false, List.of());
    }
    CollectedProduct product = read.product();
    lock(product.source(), product.sourceProductId());
    CatalogImportItem item =
        firstSave(run, product.itemKey(), product.source(), product.sourceProductId());
    ImportPlan plan = planner.plan(product);
    Applied applied = applier.apply(plan, item);

    Set<String> reasons = new LinkedHashSet<>();
    plan.allReasons().stream()
        .sorted(Comparator.naturalOrder())
        .forEach(reason -> reasons.add(reason.name()));
    reasons.addAll(applied.extraReasons());
    boolean partial = plan.isPartial() || !applied.extraReasons().isEmpty();
    item.recordResult(
        ImportItemOutcome.valueOf(plan.outcome().name()),
        partial,
        reasons,
        applied.product(),
        applied.colorsApplied(),
        null);
    em.flush();
    List<UUID> changed = applied.changedShades().stream().map(ProductShade::getId).toList();
    if (!changed.isEmpty()) {
      // 같은 트랜잭션에서 동기로 알린다. 리스너가 실패하면 색 변경도 함께 되돌아가고 이 건은 FAILED 로 남는다
      events.publishEvent(new CatalogColorChanged(new HashSet<>(changed)));
    }
    return result(item, false, changed);
  }

  /** 건 행을 먼저 저장한다. 같은 건이 이미 있으면 이 트랜잭션은 되돌리고 {@link DuplicateItemException}으로 알린다. */
  private CatalogImportItem firstSave(
      CatalogImportRun run, String itemKey, String source, String sourceProductId) {
    CatalogImportItem item = new CatalogImportItem(run, itemKey, source, sourceProductId);
    item.recordResult(ImportItemOutcome.FAILED, false, List.of(), null, 0, PROCESSING);
    try {
      return items.saveAndFlush(item);
    } catch (DataIntegrityViolationException e) {
      if (String.valueOf(e.getMostSpecificCause().getMessage())
          .contains(CatalogImportItem.RUN_ITEM_UNIQUE)) {
        throw new DuplicateItemException(e);
      }
      throw e;
    }
  }

  /** 같은 출처·상품 번호의 건을 순서대로 처리하도록 트랜잭션이 끝날 때까지 잠근다. */
  private void lock(String source, String sourceProductId) {
    jdbc.queryForList(
        "select pg_advisory_xact_lock(hashtextextended(?, 0))",
        "catalog-import:" + source + "|" + sourceProductId);
  }

  private Optional<ItemResult> existing(UUID runId, String itemKey) {
    return Optional.ofNullable(
        inNewTransaction.execute(
            status ->
                runs.findById(runId)
                    .flatMap(run -> items.findByRunAndItemKey(run, itemKey))
                    .map(item -> result(item, true, List.of()))
                    .orElse(null)));
  }

  /**
   * 처리 중 오류가 난 건을 별도 트랜잭션으로 기록한다. 그 사이에 같은 건이 다른 요청으로 이미 확정됐으면 그 결과를 그대로 돌려주고 덮어쓰지 않는다. 실패한 쪽의 건 행은
   * 롤백으로 사라지므로 지금 있는 행은 모두 다른 요청이 확정한 것이다. 동시에 두 쪽이 저장하려 하면 유니크 제약이 한쪽을 막는다.
   */
  ItemResult recordFailure(UUID runId, ReadResult read, RuntimeException cause) {
    String message = cause.getClass().getSimpleName() + ": " + cause.getMessage();
    try {
      return inNewTransaction.execute(
          status -> {
            runLock.shared(runId);
            CatalogImportRun run =
                runs.findById(runId)
                    .orElseThrow(() -> new CatalogImportRunNotFoundException(runId));
            Optional<CatalogImportItem> settled = items.findByRunAndItemKey(run, read.itemKey());
            if (settled.isPresent()) {
              return result(settled.get(), true, List.of());
            }
            CollectedProduct product = read.product();
            CatalogImportItem item =
                new CatalogImportItem(
                    run,
                    read.itemKey(),
                    product == null ? null : product.source(),
                    product == null ? null : product.sourceProductId());
            item.recordResult(ImportItemOutcome.FAILED, false, List.of(), null, 0, message);
            items.saveAndFlush(item);
            return result(item, false, List.of());
          });
    } catch (DataIntegrityViolationException e) {
      Optional<ItemResult> settled = existing(runId, read.itemKey());
      if (settled.isPresent()) {
        return settled.get();
      }
      return unrecordedFailure(runId, read, message, e);
    } catch (RuntimeException e) {
      return unrecordedFailure(runId, read, message, e);
    }
  }

  private ItemResult unrecordedFailure(
      UUID runId, ReadResult read, String message, RuntimeException e) {
    log.error("적재 실패 기록도 남기지 못했습니다. runId={}, itemKey={}", runId, read.itemKey(), e);
    return new ItemResult(
        read.itemKey(),
        ImportItemOutcome.FAILED,
        false,
        List.of(),
        null,
        0,
        false,
        false,
        message,
        List.of());
  }

  private static ItemResult result(CatalogImportItem item, boolean duplicate, List<UUID> changed) {
    return new ItemResult(
        item.getItemKey(),
        item.getOutcome(),
        item.isPartial(),
        item.getReasonCodes(),
        item.getProduct() == null ? null : item.getProduct().getId(),
        item.getColorsApplied(),
        duplicate,
        true,
        item.getMessage(),
        changed);
  }

  private static List<String> issueCodes(ReadResult read) {
    return read.issues().stream().map(i -> i.code().name()).distinct().sorted().toList();
  }

  private static String issueMessage(ReadResult read) {
    List<String> shown = new ArrayList<>();
    for (ImportIssue issue : read.issues()) {
      if (shown.size() == MAX_ISSUES_IN_MESSAGE) {
        break;
      }
      shown.add(issue.toString());
    }
    int rest = read.issues().size() - shown.size();
    return String.join("; ", shown) + (rest > 0 ? " 외 " + rest + "건" : "");
  }

  /** 같은 {@code (실행, itemKey)}가 이미 처리됐다. 트랜잭션을 되돌리기 위한 내부 신호다. */
  private static final class DuplicateItemException extends RuntimeException {
    DuplicateItemException(Throwable cause) {
      super("이미 처리된 건이다", cause);
    }
  }
}
