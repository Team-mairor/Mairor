package com.mairor.backend.products.controller;

import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.products.dto.request.CatalogDryRunRequest;
import com.mairor.backend.products.dto.request.CatalogImportBatchRequest;
import com.mairor.backend.products.dto.request.CatalogImportFileRequest;
import com.mairor.backend.products.dto.request.CatalogImportFinishRequest;
import com.mairor.backend.products.dto.request.CatalogImportStartRequest;
import com.mairor.backend.products.dto.response.CatalogDryRunResponse;
import com.mairor.backend.products.dto.response.CatalogImportBatchResponse;
import com.mairor.backend.products.dto.response.CatalogImportFileResponse;
import com.mairor.backend.products.dto.response.CatalogImportRunResponse;
import com.mairor.backend.products.dto.response.CatalogImportRunStatsResponse;
import com.mairor.backend.products.imports.CatalogDryRunService;
import com.mairor.backend.products.imports.CatalogImportFileService;
import com.mairor.backend.products.imports.CatalogImportRunService;
import com.mairor.backend.products.imports.CatalogImportRunService.RunView;
import com.mairor.backend.products.imports.CatalogImportRunService.StartCommand;
import com.mairor.backend.products.imports.CatalogImportStatsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 화장품 카탈로그 수집(내부). 수집기(S15P31A306-293)가 보낸 데이터를 DB 에 넣기 전에 어떻게 판정될지 본다. 공유 토큰 헤더({@code
 * X-Internal-Token})로 지킨다.
 *
 * <p>실행 기록이 필요한 시작·묶음 전송·종료 입구는 적재 단계(S15P31A306-295)에서 같은 판정 위에 더한다.
 */
@Tag(
    name = "운영 · 화장품 카탈로그 수집",
    description = "수집기가 보낸 상품이 카탈로그에 어떻게 반영될지 미리 본다. 공유 토큰 헤더(X-Internal-Token)가 필요하다.")
@RestController
@RequestMapping("/v1/internal/catalog/import-runs")
public class InternalCatalogImportController {

  private final CatalogDryRunService dryRunService;
  private final CatalogImportRunService runService;
  private final CatalogImportStatsService statsService;
  private final CatalogImportFileService fileService;

  public InternalCatalogImportController(
      CatalogDryRunService dryRunService,
      CatalogImportRunService runService,
      CatalogImportStatsService statsService,
      CatalogImportFileService fileService) {
    this.dryRunService = dryRunService;
    this.runService = runService;
    this.statsService = statsService;
    this.fileService = fileService;
  }

  @Operation(
      summary = "수집 상품 판정 시험",
      description =
          """
          수집한 상품 1~100건이 카탈로그에 어떻게 반영될지 건마다 판정해서 돌려준다. 아무것도 저장하지 않는다.

          - 사전 판정이다. 호출 시점의 DB 기준이라 그 사이 다른 적재나 정정이 있으면 실제 결과가 달라질 수 있다.
          - 한 건이 틀려도 요청 전체는 실패하지 않는다. 그 건만 INVALID 로 사유와 함께 돌려주고 나머지는 판정한다.
          - 사진에서 얻은 색은 설정한 임계값을 넘어야 서비스에 쓴다. 임계값을 정하기 전에는 어떤 색도 쓰지 않는 것으로 판정한다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @io.swagger.v3.oas.annotations.parameters.RequestBody(
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogDryRunRequest.class),
              examples =
                  @ExampleObject(name = "수집 상품 1건", value = CatalogImportApiDocs.DRY_RUN_REQUEST)))
  @ApiResponse(
      responseCode = "200",
      description = "건별 판정. 요청 항목과 같은 순서.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogDryRunResponse.class),
              examples =
                  @ExampleObject(name = "판정 결과", value = CatalogImportApiDocs.DRY_RUN_RESPONSE)))
  @ApiResponse(
      responseCode = "400",
      description = "items 가 배열이 아니거나 비었거나 100건을 넘는다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(
                      name = "VALIDATION_FAILED",
                      value = CatalogImportApiDocs.ITEMS_TOO_MANY)))
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @PostMapping("/dry-run")
  public CatalogDryRunResponse dryRun(@RequestBody CatalogDryRunRequest request) {
    return dryRunService.dryRun(request);
  }

  @Operation(
      summary = "적재 실행 열기",
      description =
          """
          수집기가 한 번 돌린 실행을 연다. 이후 건 묶음·하트비트·끝내기는 응답의 id 로 보낸다.

          - 진행 중인 runId 를 다시 열면 같은 실행을 이어 쓰고 resumed 가 true 다(200). 새로 열면 201 이다.
          - 이미 끝난 runId 는 다시 열 수 없다. 새 runId 로 시작한다.
          - 하트비트가 제한 시간 동안 없으면 서버가 실행을 ABANDONED 로 끝낸다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "201",
      description = "새 실행을 열었다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogImportRunResponse.class),
              examples = @ExampleObject(name = "열린 실행", value = CatalogImportApiDocs.RUN_RESPONSE)))
  @ApiResponse(responseCode = "200", description = "진행 중이던 같은 runId 의 실행을 이어 쓴다.")
  @ApiResponse(responseCode = "400", description = "runId 가 없거나 값이 길이 제한을 넘는다. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "409", description = "같은 runId 의 실행이 이미 끝났다. (IMPORT_RUN_CLOSED)")
  @PostMapping
  public ResponseEntity<CatalogImportRunResponse> start(
      @Valid @RequestBody CatalogImportStartRequest request) {
    RunView view =
        runService.start(
            new StartCommand(
                request.runId(),
                request.seed(),
                request.collectorVersion(),
                request.startedAt() == null ? null : request.startedAt().toInstant(),
                request.resultFile()));
    return ResponseEntity.status(view.resumed() ? HttpStatus.OK : HttpStatus.CREATED)
        .body(CatalogImportRunResponse.from(view));
  }

  @Operation(
      summary = "수집 상품 묶음 적재",
      description =
          """
          수집 상품 1~100건을 건마다 카탈로그에 반영하고 건별 결과를 돌려준다.

          - 건마다 자기 트랜잭션이다. 한 건이 틀리거나 실패해도 그 건만 INVALID·FAILED 로 기록하고 나머지는 계속한다.
          - 같은 건(itemKey)을 다시 보내면 한 번만 처리하고 저장된 결과를 duplicate=true 로 돌려준다. 묶음을 다시 보내도 안전하다.
          - 받을 때마다 하트비트가 갱신된다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @io.swagger.v3.oas.annotations.parameters.RequestBody(
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogImportBatchRequest.class),
              examples =
                  @ExampleObject(name = "수집 상품 1건", value = CatalogImportApiDocs.DRY_RUN_REQUEST)))
  @ApiResponse(
      responseCode = "200",
      description = "건별 결과. 요청 항목과 같은 순서.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogImportBatchResponse.class),
              examples =
                  @ExampleObject(name = "적재 결과", value = CatalogImportApiDocs.BATCH_RESPONSE)))
  @ApiResponse(
      responseCode = "400",
      description = "items 가 배열이 아니거나 비었거나 100건을 넘는다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(
                      name = "VALIDATION_FAILED",
                      value = CatalogImportApiDocs.ITEMS_TOO_MANY)))
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "실행을 찾을 수 없다. (IMPORT_RUN_NOT_FOUND)")
  @ApiResponse(
      responseCode = "409",
      description = "실행이 이미 끝났다(완료·실패·하트비트 끊김). (IMPORT_RUN_CLOSED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(
                      name = "IMPORT_RUN_CLOSED",
                      value = CatalogImportApiDocs.RUN_CLOSED)))
  @PostMapping("/{id}/items")
  public CatalogImportBatchResponse importItems(
      @PathVariable UUID id, @RequestBody CatalogImportBatchRequest request) {
    return CatalogImportBatchResponse.from(runService.importBatch(id, request.items()));
  }

  @Operation(
      summary = "적재 실행 하트비트",
      description =
          """
          진행 중인 실행이 살아 있다고 알린다. 건을 보내지 않는 긴 시간에도 실행이 끊긴 것으로 처리되지 않게 한다.

          - 건 묶음을 보낼 때도 하트비트가 갱신되므로 건을 계속 보내는 동안에는 따로 부를 필요가 없다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "200",
      description = "실행의 현재 모습.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogImportRunResponse.class),
              examples =
                  @ExampleObject(name = "진행 중인 실행", value = CatalogImportApiDocs.RUN_RESPONSE)))
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "실행을 찾을 수 없다. (IMPORT_RUN_NOT_FOUND)")
  @ApiResponse(responseCode = "409", description = "실행이 이미 끝났다. (IMPORT_RUN_CLOSED)")
  @PostMapping("/{id}/heartbeat")
  public CatalogImportRunResponse heartbeat(@PathVariable UUID id) {
    return CatalogImportRunResponse.from(runService.heartbeat(id));
  }

  @Operation(
      summary = "적재 실행 끝내기",
      description =
          """
          실행을 COMPLETED(끝까지 보냄) 또는 FAILED(수집기가 실패로 끝냄)로 끝낸다.

          - 같은 상태로 다시 부르면 그대로 성공한다. 다른 상태로 이미 끝났으면 거절한다.
          - 건별 실패는 실행의 결과가 아니라 건에 남는다. 건이 실패했어도 COMPLETED 로 끝낼 수 있다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "200",
      description = "끝난 실행의 모습.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogImportRunResponse.class)))
  @ApiResponse(
      responseCode = "400",
      description = "status 가 없거나 COMPLETED·FAILED 가 아니다. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "실행을 찾을 수 없다. (IMPORT_RUN_NOT_FOUND)")
  @ApiResponse(responseCode = "409", description = "이미 다른 상태로 끝났다. (IMPORT_RUN_CLOSED)")
  @PostMapping("/{id}/finish")
  public CatalogImportRunResponse finish(
      @PathVariable UUID id, @Valid @RequestBody CatalogImportFinishRequest request) {
    return CatalogImportRunResponse.from(runService.finish(id, request.status().toRunStatus()));
  }

  @Operation(
      summary = "적재 실행 통계",
      description =
          """
          한 실행이 어떻게 끝났는지 건의 처리 결과별 개수와 색 칸 반영 수로 돌려준다.

          - 실행이 COMPLETED 여도 틀린 건·실패한 건은 failed 와 problems 에 그대로 나온다.
          - 지금 카탈로그의 색 상태가 아니라 이 실행이 한 일이다. 현재 상태는 카탈로그 색 품질 통계에서 본다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "200",
      description = "실행 통계.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogImportRunStatsResponse.class)))
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "실행을 찾을 수 없다. (IMPORT_RUN_NOT_FOUND)")
  @GetMapping("/{id}/stats")
  public CatalogImportRunStatsResponse stats(@PathVariable UUID id) {
    return CatalogImportRunStatsResponse.from(statsService.runStats(id));
  }

  @Operation(
      summary = "실행 결과 파일 적재",
      description =
          """
          수집기가 만든 실행 결과 파일(JSONL)을 읽어 건마다 카탈로그에 반영한다. 초기 데이터 운영 적재와 틀린 건 재처리가 쓴다.

          - 한 번에 새로 처리하는 건은 limit 까지다. finished 가 false 면 같은 요청을 다시 보낸다. 이미 처리한 건은 건너뛰고 이어서 처리한다.
          - retryOf 에 이전 실행의 id 를 주면 그 실행에서 FAILED·INVALID 로 끝난 건만 같은 파일에서 다시 읽어 새 실행으로 처리한다. 이전 실행의 기록은 그대로 남는다.
          - 파일 이름은 상대 이름만 받는다. 운영은 객체 저장소의 catalog-runs/ 에서 받아 읽는다. 없는 파일은 404 이다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(
      responseCode = "200",
      description = "이번 호출의 처리 결과와 실행 통계.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = CatalogImportFileResponse.class)))
  @ApiResponse(
      responseCode = "400",
      description =
          "파일 이름이 규칙에 맞지 않거나, header 가 없거나, limit 가 범위를 벗어나거나, 재처리할 실행의 파일과 다르다. (INVALID_RESULT_FILE, VALIDATION_FAILED, RETRY_FILE_MISMATCH)")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(
      responseCode = "404",
      description = "파일이 저장소에 없거나 재처리할 실행이 없다. (RESULT_FILE_NOT_FOUND, IMPORT_RUN_NOT_FOUND)")
  @ApiResponse(
      responseCode = "409",
      description = "같은 runId 의 실행이 실패하거나 하트비트가 끊겨 끝났다. 새 실행으로 다시 시작한다. (IMPORT_RUN_CLOSED)")
  @ApiResponse(
      responseCode = "503",
      description = "저장소에서 결과 파일을 받지 못했다. 잠시 후 다시 보낸다. (SERVICE_UNAVAILABLE)")
  @PostMapping("/from-file")
  public CatalogImportFileResponse importFile(
      @Valid @RequestBody CatalogImportFileRequest request) {
    return CatalogImportFileResponse.from(
        fileService.importFile(request.resultFile(), request.limit(), request.retryOf()));
  }
}
