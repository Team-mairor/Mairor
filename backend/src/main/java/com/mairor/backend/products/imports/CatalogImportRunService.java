package com.mairor.backend.products.imports;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.products.entity.CatalogImportRun;
import com.mairor.backend.products.entity.ImportRunStatus;
import com.mairor.backend.products.imports.CatalogImportService.ItemResult;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.JsonNode;

/**
 * 카탈로그 적재 실행의 생명주기: 열기, 하트비트, 건 묶음 보내기, 끝내기, 끊긴 실행 정리.
 *
 * <ul>
 *   <li><b>열기</b>는 수집기의 {@code runId}가 키다. 이미 진행 중인 {@code runId}를 다시 열면 같은 실행을 이어 쓴다(끊긴 수집기가 이어서
 *       보내는 경우). 이미 끝난 {@code runId}는 다시 열 수 없다.
 *   <li><b>건 묶음</b>은 1~{@value #MAX_ITEMS}건이다. 건마다 {@link CatalogImportService}가 따로 처리하므로 한 건이 틀리거나
 *       실패해도 나머지는 계속된다. 같은 건을 다시 보내도(묶음 재전송, 동시 재전송 포함) 한 번만 처리하고 저장된 결과를 돌려준다. 묶음을 받을 때마다 하트비트가
 *       갱신된다.
 *   <li><b>끝내기</b>는 같은 상태로 다시 부르면 그대로 성공하고, 다른 상태로 부르면 거절한다.
 *   <li><b>끊긴 실행</b>은 마지막 하트비트가 {@code catalog.import.heartbeat-timeout}보다 오래되면 {@code ABANDONED}로
 *       끝낸다. 상태 변경은 모두 조건부 갱신이라, 정리 작업이 끝낸 실행을 건 전송이 되살리지 못한다.
 * </ul>
 */
@Service
public class CatalogImportRunService {

  public static final int MAX_ITEMS = 100;

  private static final Logger log = LoggerFactory.getLogger(CatalogImportRunService.class);

  private final CatalogImportRunRepository runs;
  private final CatalogImportService items;
  private final CatalogImportProperties properties;
  private final Clock clock;
  private final CatalogRunLock runLock;
  private final TransactionTemplate inNewTransaction;

  public CatalogImportRunService(
      CatalogImportRunRepository runs,
      CatalogImportService items,
      CatalogImportProperties properties,
      Clock clock,
      CatalogRunLock runLock,
      PlatformTransactionManager transactionManager) {
    this.runs = runs;
    this.items = items;
    this.properties = properties;
    this.clock = clock;
    this.runLock = runLock;
    this.inNewTransaction = new TransactionTemplate(transactionManager);
    this.inNewTransaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
  }

  /**
   * 실행 열기 요청.
   *
   * @param runId 수집기가 실행 결과 파일 header 에 쓴 {@code runId}
   * @param seed header 의 {@code seed}
   * @param collectorStartedAt header 의 {@code startedAt}
   * @param resultFile 실행 결과 파일 이름(저장소 catalog-runs/ 아래 상대 이름)
   */
  public record StartCommand(
      String runId,
      String seed,
      String collectorVersion,
      Instant collectorStartedAt,
      String resultFile) {}

  /**
   * 실행의 현재 모습.
   *
   * @param resumed 이미 진행 중이던 실행을 다시 열어 이어 쓰는 것인가
   */
  public record RunView(
      UUID id,
      String runId,
      ImportRunStatus status,
      Instant collectorStartedAt,
      Instant lastHeartbeatAt,
      Instant finishedAt,
      boolean resumed) {

    static RunView of(CatalogImportRun run, boolean resumed) {
      return new RunView(
          run.getId(),
          run.getRunId(),
          run.getStatus(),
          run.getCollectorStartedAt(),
          run.getLastHeartbeatAt(),
          run.getFinishedAt(),
          resumed);
    }
  }

  /**
   * 실행을 연다. 진행 중인 같은 {@code runId}가 있으면 이어 쓴다.
   *
   * @throws CatalogImportRunClosedException 같은 {@code runId}의 실행이 이미 끝났으면
   * @throws IllegalArgumentException 값이 길이 제한을 넘으면
   */
  public RunView start(StartCommand command) {
    Instant now = clock.instant();
    CatalogImportRun existing = runs.findByRunId(command.runId()).orElse(null);
    if (existing != null) {
      return resume(existing);
    }
    try {
      CatalogImportRun created =
          inNewTransaction.execute(
              status ->
                  runs.saveAndFlush(
                      new CatalogImportRun(
                          command.runId(),
                          command.seed(),
                          command.collectorVersion(),
                          command.resultFile(),
                          command.collectorStartedAt(),
                          now)));
      return RunView.of(created, false);
    } catch (DataIntegrityViolationException e) {
      // 같은 runId 를 동시에 연 쪽이 먼저 저장했다. 그 실행을 이어 쓴다
      return resume(runs.findByRunId(command.runId()).orElseThrow(() -> e));
    }
  }

  private RunView resume(CatalogImportRun existing) {
    if (existing.getStatus().isFinished()) {
      throw new CatalogImportRunClosedException(existing.getRunId(), existing.getStatus());
    }
    touch(existing.getId());
    return RunView.of(runs.findById(existing.getId()).orElse(existing), true);
  }

  /** 하트비트를 보낸다. 건을 보내지 않는 긴 시간에도 실행이 끊긴 것으로 처리되지 않게 한다. */
  public RunView heartbeat(UUID id) {
    touch(id);
    return get(id, false);
  }

  /**
   * 건 묶음을 처리한다. 묶음 전체가 실패하지 않고 건마다 결과가 돌아온다.
   *
   * @param rawItems 수집 상품 1~{@value #MAX_ITEMS}건의 배열
   * @throws BusinessException 400 {@code VALIDATION_FAILED}: 배열이 아니거나 비었거나 너무 많으면
   * @throws CatalogImportRunNotFoundException 실행이 없으면
   * @throws CatalogImportRunClosedException 실행이 이미 끝났으면
   */
  public List<ItemResult> importBatch(UUID id, JsonNode rawItems) {
    if (rawItems == null || !rawItems.isArray()) {
      throw invalid("items 는 배열이어야 합니다.");
    }
    if (rawItems.isEmpty()) {
      throw invalid("items 는 1건 이상이어야 합니다.");
    }
    if (rawItems.size() > MAX_ITEMS) {
      throw invalid("items 는 " + MAX_ITEMS + "건까지입니다.");
    }
    touch(id);
    List<ItemResult> results = new ArrayList<>(rawItems.size());
    for (JsonNode raw : rawItems) {
      results.add(items.importItem(id, raw));
    }
    runs.touchIfRunning(id, clock.instant());
    return List.copyOf(results);
  }

  /**
   * 실행을 끝낸다. 같은 상태로 다시 부르면 그대로 성공한다.
   *
   * @param end {@code COMPLETED}(수집기가 끝났다고 알림) 또는 {@code FAILED}(수집기가 실패로 끝냄)
   * @throws IllegalArgumentException {@code end}가 끝내는 상태가 아니거나 {@code ABANDONED}이면(그 상태는 서버만 정한다)
   * @throws CatalogImportRunClosedException 이미 다른 상태로 끝났으면
   */
  public RunView finish(UUID id, ImportRunStatus end) {
    if (end != ImportRunStatus.COMPLETED && end != ImportRunStatus.FAILED) {
      throw new IllegalArgumentException("수집기가 정할 수 있는 끝 상태는 COMPLETED·FAILED 다: " + end);
    }
    CatalogImportRun run =
        runs.findById(id).orElseThrow(() -> new CatalogImportRunNotFoundException(id));
    if (run.getStatus() == end) {
      return RunView.of(run, false);
    }
    if (run.getStatus().isFinished()) {
      throw new CatalogImportRunClosedException(run.getRunId(), run.getStatus());
    }
    // 진행 중인 건이 모두 확정된 뒤에 끝낸다. 끝난 뒤에는 새 건이 들어오지 못한다
    Integer changed =
        inNewTransaction.execute(
            status -> {
              runLock.exclusive(id);
              return runs.finishIfRunning(id, end, clock.instant());
            });
    if (changed == null || changed == 0) {
      // 읽은 뒤에 다른 쪽(정리 작업이나 다른 호출)이 먼저 끝냈다
      CatalogImportRun latest =
          runs.findById(id).orElseThrow(() -> new CatalogImportRunNotFoundException(id));
      if (latest.getStatus() == end) {
        return RunView.of(latest, false);
      }
      throw new CatalogImportRunClosedException(latest.getRunId(), latest.getStatus());
    }
    return get(id, false);
  }

  /** 실행 하나를 읽는다. */
  public RunView get(UUID id) {
    return get(id, false);
  }

  /**
   * 하트비트가 제한을 넘긴 진행 중 실행을 {@code ABANDONED}로 끝낸다.
   *
   * @return 끝낸 실행 수
   */
  public int abandonStale() {
    Instant now = clock.instant();
    Instant cutoff = now.minus(properties.heartbeatTimeout());
    int count = 0;
    for (UUID id : runs.findStaleIds(cutoff)) {
      Integer changed =
          inNewTransaction.execute(
              status -> {
                runLock.exclusive(id);
                return runs.abandonIfStale(id, cutoff, now);
              });
      count += changed == null ? 0 : changed;
    }
    if (count > 0) {
      log.warn("하트비트가 끊긴 적재 실행을 ABANDONED 로 끝냈습니다. 건수={}", count);
    }
    return count;
  }

  private void touch(UUID id) {
    if (runs.touchIfRunning(id, clock.instant()) > 0) {
      return;
    }
    CatalogImportRun run =
        runs.findById(id).orElseThrow(() -> new CatalogImportRunNotFoundException(id));
    if (run.getStatus().isFinished()) {
      throw new CatalogImportRunClosedException(run.getRunId(), run.getStatus());
    }
  }

  private RunView get(UUID id, boolean resumed) {
    return RunView.of(
        runs.findById(id).orElseThrow(() -> new CatalogImportRunNotFoundException(id)), resumed);
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
