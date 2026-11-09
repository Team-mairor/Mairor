package com.mairor.backend.products.imports;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.products.entity.CatalogImportRun;
import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.entity.ImportRunStatus;
import com.mairor.backend.products.imports.CatalogImportRunService.RunView;
import com.mairor.backend.products.imports.CatalogImportRunService.StartCommand;
import com.mairor.backend.products.imports.CatalogImportService.ItemResult;
import com.mairor.backend.products.imports.CatalogImportStatsService.RunStats;
import com.mairor.backend.products.imports.CatalogRunFileReader.Header;
import com.mairor.backend.products.repository.CatalogImportItemRepository;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

/**
 * 수집기가 만든 실행 결과 파일(JSONL)을 읽어 카탈로그에 적재한다. 초기 데이터 운영 적재(S15P31A306-317)와 틀린 건 재처리가 이 입구를 쓴다.
 *
 * <p>파일 header 의 {@code runId}로 실행을 열고(이미 진행 중이면 이어 쓴다), 건마다 {@link CatalogImportService}로 처리한다. 한
 * 번의 호출은 새로 처리하는 건을 {@code limit}건까지만 처리하고 돌려준다. 요청 하나가 너무 오래 걸리지 않게 하려는 것이다. 파일 끝까지 읽었으면 실행을
 * {@code COMPLETED}로 끝낸다 ({@code finished=true}). 끝나지 않았으면 같은 요청을 다시 보내면 된다. 이미 처리한 건은 건너뛰고(저장된 결과를
 * 돌려받을 뿐 다시 반영하지 않는다) 이어서 처리한다. 끝난 뒤에 다시 보내도 아무 일도 하지 않는다.
 *
 * <p><b>틀린 건 재처리({@code retryOf})</b>: 이전 실행에서 {@code FAILED}·{@code INVALID}로 끝난 건만 같은 파일에서 다시 읽어
 * 새 실행({@code <이전 runId>-retry})으로 처리한다. 끝난 실행의 기록을 고쳐 쓰지 않고, 이전 실행의 통계와 실패 기록은 그대로 남는다. 수집기가 파일을
 * 고쳐 다시 만든 것이 아니라 같은 파일의 같은 줄을 다시 처리하므로, 서버 쪽 일시 오류로 실패한 건에 쓴다. 파일을 읽지 못한 줄(중간이 깨진 줄)은 건으로 세지 않고
 * {@code unreadable}로 알린다.
 */
@Service
public class CatalogImportFileService {

  public static final int DEFAULT_LIMIT = 500;
  public static final int MAX_LIMIT = 2000;

  private static final int HEARTBEAT_EVERY = 50;
  private static final List<ImportItemOutcome> RETRYABLE =
      List.of(ImportItemOutcome.FAILED, ImportItemOutcome.INVALID);

  private final CatalogRunFileReader reader;
  private final CatalogImportRunService runService;
  private final CatalogImportService itemService;
  private final CatalogImportStatsService statsService;
  private final CatalogImportRunRepository runs;
  private final CatalogImportItemRepository items;

  public CatalogImportFileService(
      CatalogRunFileReader reader,
      CatalogImportRunService runService,
      CatalogImportService itemService,
      CatalogImportStatsService statsService,
      CatalogImportRunRepository runs,
      CatalogImportItemRepository items) {
    this.reader = reader;
    this.runService = runService;
    this.itemService = itemService;
    this.statsService = statsService;
    this.runs = runs;
    this.items = items;
  }

  /**
   * 한 번의 호출 결과.
   *
   * @param processed 이번 호출에서 새로 처리한 건 수(이미 처리한 건은 세지 않는다)
   * @param unreadable 읽지 못해 건너뛴 줄 수(이번 호출이 훑은 범위)
   * @param unrecorded itemKey 가 없어 기록할 곳이 없는 틀린 줄 수(이번 호출이 훑은 범위). 처리 건 수에 세지 않는다
   * @param finished 파일 끝까지 처리해 실행을 끝냈는가
   */
  public record FileImportResult(
      RunView run,
      int processed,
      int unreadable,
      int unrecorded,
      boolean finished,
      RunStats stats) {}

  /**
   * 파일을 적재한다.
   *
   * @param resultFile 실행 결과 폴더 안의 파일 상대 이름
   * @param limit 이번 호출에서 새로 처리할 최대 건 수. 없으면 {@value #DEFAULT_LIMIT}
   * @param retryOf 다시 처리할 이전 실행의 id. 있으면 그 실행에서 실패·틀린 건만 처리한다
   * @throws BusinessException 400 {@code INVALID_RESULT_FILE}·{@code VALIDATION_FAILED}, 404 {@code
   *     RESULT_FILE_NOT_FOUND}
   * @throws CatalogImportRunClosedException 같은 실행이 실패하거나 끊겨 끝났으면
   */
  public FileImportResult importFile(String resultFile, Integer limit, UUID retryOf) {
    int max = limit == null ? DEFAULT_LIMIT : limit;
    if (max < 1 || max > MAX_LIMIT) {
      throw new BusinessException(
          HttpStatus.BAD_REQUEST, "VALIDATION_FAILED", "limit 는 1~" + MAX_LIMIT + " 이어야 합니다.");
    }
    Path file = reader.resolve(resultFile);
    Header header = reader.header(file);

    Set<String> only = null;
    String runId = header.runId();
    if (retryOf != null) {
      CatalogImportRun previous =
          runs.findById(retryOf).orElseThrow(() -> new CatalogImportRunNotFoundException(retryOf));
      if (!resultFile.equals(previous.getResultFile())) {
        throw new BusinessException(
            HttpStatus.BAD_REQUEST, "RETRY_FILE_MISMATCH", "재처리는 이전 실행과 같은 파일에서만 할 수 있습니다.");
      }
      only = new HashSet<>(items.findItemKeysByRunIdAndOutcomeIn(retryOf, RETRYABLE));
      runId = previous.getRunId() + "-retry";
    }

    CatalogImportRun existing = runs.findByRunId(runId).orElse(null);
    if (existing != null && existing.getStatus() == ImportRunStatus.COMPLETED) {
      return result(existing.getId(), 0, 0, 0, true);
    }
    RunView run =
        runService.start(
            new StartCommand(
                runId, header.seed(), header.collectorVersion(), header.startedAt(), resultFile));

    int[] processed = {0};
    int[] unreadable = {0};
    int[] unrecorded = {0};
    Set<String> wanted = only;
    boolean reachedEnd =
        reader.forEachLine(
            file,
            line -> {
              JsonNode collected = line.node() == null ? null : line.node().path("collected");
              if (collected == null || !collected.isObject()) {
                unreadable[0]++;
                return true;
              }
              if (wanted != null && !wanted.contains(line.node().path("itemKey").asString(null))) {
                return true;
              }
              ItemResult result = itemService.importItem(run.id(), collected);
              if (!result.recorded() && result.outcome() == ImportItemOutcome.INVALID) {
                // 건 행을 남길 수 없어 다음 호출도 같은 줄을 다시 만난다. 한도와 진행에 세면 뒤의 정상 건에 닿지 못한다
                unrecorded[0]++;
                return true;
              }
              if (!result.duplicate()) {
                processed[0]++;
                if (processed[0] % HEARTBEAT_EVERY == 0) {
                  runService.heartbeat(run.id());
                }
              }
              return processed[0] < max;
            });
    if (reachedEnd) {
      runService.finish(run.id(), ImportRunStatus.COMPLETED);
    }
    return result(run.id(), processed[0], unreadable[0], unrecorded[0], reachedEnd);
  }

  private FileImportResult result(
      UUID runId, int processed, int unreadable, int unrecorded, boolean finished) {
    RunStats stats = statsService.runStats(runId);
    return new FileImportResult(stats.run(), processed, unreadable, unrecorded, finished, stats);
  }
}
