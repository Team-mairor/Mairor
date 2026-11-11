package com.mairor.backend.executions.controller;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.executions.dto.CreateExecutionRequest;
import com.mairor.backend.executions.dto.ExecutionAbandonmentResponse;
import com.mairor.backend.executions.dto.ExecutionCompletionResponse;
import com.mairor.backend.executions.dto.ExecutionResponse;
import com.mairor.backend.executions.dto.PhotoConsentRequest;
import com.mairor.backend.executions.dto.PhotoConsentResponse;
import com.mairor.backend.executions.service.ExecutionCompletionService;
import com.mairor.backend.executions.service.ExecutionCreationService;
import com.mairor.backend.executions.service.ExecutionLifecycleService;
import com.mairor.backend.executions.service.ExecutionPhotoService;
import com.mairor.backend.executions.service.ExecutionQueryService;
import com.mairor.backend.photos.dto.PhotoResponse;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Tag(name = "가이드 실행", description = "시작 당시의 가이드·제품·선택 스냅샷을 저장하고 조회한다.")
@RestController
@RequestMapping("/v1/users/me/executions")
public class GuideExecutionController {
  private final ExecutionCreationService creation;
  private final ExecutionQueryService query;
  private final ExecutionPhotoService photos;
  private final ExecutionCompletionService completion;
  private final ExecutionLifecycleService lifecycle;

  public GuideExecutionController(
      ExecutionCreationService creation,
      ExecutionQueryService query,
      ExecutionPhotoService photos,
      ExecutionCompletionService completion,
      ExecutionLifecycleService lifecycle) {
    this.creation = creation;
    this.query = query;
    this.photos = photos;
    this.completion = completion;
    this.lifecycle = lifecycle;
  }

  @Operation(
      summary = "가이드 실행 생성",
      description = "최신 매칭·본인 선택·기준 얼굴을 검증하고 실행을 생성한다. 같은 세션의 이전 진행 실행은 새 요청 성공 시에만 종료한다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "201", description = "시작 당시 선택 스냅샷과 IN_PROGRESS 실행.")
  @ApiResponse(
      responseCode = "400",
      description = "필수 입력 또는 단계 선택이 잘못됐다. (VALIDATION_FAILED, GUIDE_SELECTION_INVALID)")
  @ApiResponse(
      responseCode = "409",
      description =
          "재매칭·새 얼굴 등록·제품 없음 확인이 필요하다. (GUIDE_MATCH_STALE, FACE_REGISTRATION_ALREADY_USED, GUIDE_MISSING_PRODUCTS_NOT_ACKNOWLEDGED)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.NotFound
  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public ExecutionResponse create(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest servletRequest,
      @Valid @RequestBody CreateExecutionRequest request) {
    return creation.create(principal.userId(), sessionId(servletRequest), request);
  }

  @Operation(
      summary = "가이드 실행 조회",
      description =
          "진행 실행은 본인 원래 세션, 완료 실행은 본인 계정에서 저장 스냅샷을 조회한다. 포기한 실행은 404다. 새로고침 이어 하기 기능은 제공하지 않는다.",
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "저장된 실행·단계 선택과 현재 사진 메타데이터. Cache-Control: no-store.")
  @ApiResponse(responseCode = "400", description = "executionId 형식이 잘못됐다. (VALIDATION_FAILED)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.NotFound
  @GetMapping("/{executionId}")
  public ResponseEntity<ExecutionResponse> get(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest request,
      @PathVariable UUID executionId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(query.get(principal.userId(), sessionId(request), executionId));
  }

  @Operation(
      summary = "실행 사진 저장 동의 변경",
      description = "현재 실행의 사진 저장 동의 여부와 정책 버전·시각을 기록한다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "200", description = "사진 동의가 기록됐다.")
  @ApiResponse(responseCode = "409", description = "실행 종료 상태다. (GUIDE_EXECUTION_NOT_ACTIVE)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.NotFound
  @PatchMapping("/{executionId}/photo-consent")
  public PhotoConsentResponse setPhotoConsent(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest request,
      @PathVariable UUID executionId,
      @Valid @RequestBody PhotoConsentRequest body) {
    return photos.setConsent(principal.userId(), sessionId(request), executionId, body.enabled());
  }

  @Operation(
      summary = "가이드 단계 사진 저장",
      description = "동의한 진행 실행의 선택 단계에 JPEG/PNG 사진을 저장한다. 새 사진 연결 성공 후 이전 사진을 정리한다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "200", description = "저장된 단계 사진 메타데이터.")
  @ApiResponse(
      responseCode = "409",
      description =
          "실행 상태·동의·단계 정책과 충돌했다. (GUIDE_EXECUTION_NOT_ACTIVE, GUIDE_PHOTO_CONSENT_REQUIRED, GUIDE_STEP_PHOTO_NOT_ALLOWED)")
  @ApiResponse(responseCode = "413", description = "사진 파일 크기 또는 해상도 상한을 초과했다. (PAYLOAD_TOO_LARGE)")
  @ApiResponse(
      responseCode = "415",
      description = "JPEG/PNG 이미지가 아니거나 디코딩할 수 없다. (UNSUPPORTED_MEDIA_TYPE)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.NotFound
  @PutMapping(
      value = "/{executionId}/steps/{stepId}/photo",
      consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
      produces = MediaType.APPLICATION_JSON_VALUE)
  public PhotoResponse uploadStepPhoto(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest request,
      @PathVariable UUID executionId,
      @PathVariable String stepId,
      @RequestPart("image") MultipartFile image) {
    return photos.upload(principal.userId(), sessionId(request), executionId, stepId, image);
  }

  @Operation(
      summary = "가이드 실행 완료",
      description = "완료 시점의 리포트 스냅샷을 한 건 생성하고 얼굴 등록을 보관한다. 재요청은 같은 기록 ID를 반환한다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "201", description = "처음 완료한 실행과 생성한 recordId.")
  @ApiResponse(responseCode = "200", description = "이미 완료된 실행의 동일 recordId.")
  @ApiResponse(responseCode = "409", description = "포기된 실행은 완료할 수 없다. (GUIDE_EXECUTION_NOT_ACTIVE)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.NotFound
  @PostMapping("/{executionId}/completion")
  public ResponseEntity<ExecutionCompletionResponse> complete(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest request,
      @PathVariable UUID executionId) {
    var result = completion.complete(principal.userId(), sessionId(request), executionId);
    return ResponseEntity.status(result.newlyCompleted() ? HttpStatus.CREATED : HttpStatus.OK)
        .body(result.response());
  }

  @Operation(
      summary = "가이드 실행 중도 종료",
      description = "진행 중 실행의 사진 접근을 차단하고 단계·얼굴 등록 사진 정리를 예약한다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "200", description = "실행 종료 및 사진 정리 상태.")
  @ApiResponse(
      responseCode = "409",
      description = "완료된 실행은 종료할 수 없다. (GUIDE_EXECUTION_ALREADY_COMPLETED)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.NotFound
  @PostMapping("/{executionId}/abandonment")
  public ExecutionAbandonmentResponse abandon(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest request,
      @PathVariable UUID executionId) {
    return lifecycle.abandon(principal.userId(), sessionId(request), executionId);
  }

  private String sessionId(HttpServletRequest request) {
    var session = request.getSession(false);
    if (session == null) {
      throw new BusinessException(ErrorCode.UNAUTHORIZED);
    }
    return session.getId();
  }
}
