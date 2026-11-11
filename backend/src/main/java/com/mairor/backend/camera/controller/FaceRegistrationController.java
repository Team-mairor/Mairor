package com.mairor.backend.camera.controller;

import com.mairor.backend.camera.dto.FaceRegistrationRequest;
import com.mairor.backend.camera.dto.FaceRegistrationResponse;
import com.mairor.backend.camera.service.FaceRegistrationService;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Encoding;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Tag(name = "얼굴 등록", description = "가이드 실행마다 사용할 기준 얼굴 사진을 등록하고 관리한다.")
@RestController
@RequestMapping("/v1/users/me/face-registrations")
public class FaceRegistrationController {
  private final FaceRegistrationService registrations;

  public FaceRegistrationController(FaceRegistrationService registrations) {
    this.registrations = registrations;
  }

  @Operation(
      summary = "기준 얼굴 등록",
      requestBody =
          @io.swagger.v3.oas.annotations.parameters.RequestBody(
              required = true,
              content =
                  @Content(
                      mediaType = MediaType.MULTIPART_FORM_DATA_VALUE,
                      encoding =
                          @Encoding(
                              name = "metadata",
                              contentType = MediaType.APPLICATION_JSON_VALUE))),
      description =
          """
      실행에 사용할 본인 기준 얼굴 사진과 촬영 조건을 등록한다.
      - 필수 촬영 조건과 등록 안내 동의를 확인한다.
      - 같은 세션·영상의 이전 미연결 등록은 새 등록 성공 후 폐기한다.
      - 서버 얼굴 인식 대신 클라이언트 촬영 조건 판정을 기록한다.
      """,
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(
      responseCode = "201",
      description = "기준 얼굴 등록에 성공했다.",
      content = @Content(schema = @Schema(implementation = FaceRegistrationResponse.class)))
  @ApiResponse(
      responseCode = "400",
      description =
          "입력·동의·안내 버전·촬영 조건이 잘못됐다. (VALIDATION_FAILED, FACE_CONSENT_REQUIRED, FACE_NOTICE_VERSION_INVALID, FACE_CONDITIONS_NOT_MET)")
  @ApiResponse(responseCode = "413", description = "사진 파일 크기 또는 해상도 상한을 초과했다. (PAYLOAD_TOO_LARGE)")
  @ApiResponse(
      responseCode = "415",
      description = "JPEG/PNG 사진 형식이 아니거나 디코딩할 수 없다. (UNSUPPORTED_MEDIA_TYPE)")
  @ApiResponse(responseCode = "503", description = "사진 저장소를 처리하지 못했다. (SERVICE_UNAVAILABLE)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.NotFound
  @PostMapping(
      consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
      produces = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.CREATED)
  public FaceRegistrationResponse register(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest servletRequest,
      @RequestPart("metadata") @Valid FaceRegistrationRequest metadata,
      @RequestPart("image") MultipartFile image) {
    return registrations.register(principal.userId(), sessionId(servletRequest), metadata, image);
  }

  @Operation(
      summary = "기준 얼굴 조회",
      description =
          """
      본인 얼굴 등록 상태와 사진 메타데이터를 조회한다.
      - 미연결·진행 등록은 원래 로그인 세션에서만 조회한다.
      - 완료 리포트 보관 등록은 본인 계정에서 조회한다.
      """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "얼굴 등록과 사진 메타데이터.",
      content = @Content(schema = @Schema(implementation = FaceRegistrationResponse.class)))
  @ApiResponse(responseCode = "400", description = "등록 ID 형식이 잘못됐다. (VALIDATION_FAILED)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.NotFound
  @GetMapping(value = "/{faceRegistrationId}", produces = MediaType.APPLICATION_JSON_VALUE)
  public FaceRegistrationResponse get(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest servletRequest,
      @PathVariable UUID faceRegistrationId) {
    return registrations.get(principal.userId(), sessionId(servletRequest), faceRegistrationId);
  }

  @Operation(
      summary = "기준 얼굴 삭제",
      description =
          """
      본인 미연결 얼굴 등록과 사진 파일을 폐기한다.
      - 실행·완료 리포트에 연결된 등록은 해당 실행·리포트에서 정리한다.
      - 파일 삭제가 끝나야 성공하며 실패한 요청은 같은 ID로 재시도한다.
      """,
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "204", description = "얼굴 등록 사진 삭제를 완료했다.")
  @ApiResponse(responseCode = "400", description = "등록 ID 형식이 잘못됐다. (VALIDATION_FAILED)")
  @ApiResponse(
      responseCode = "409",
      description = "실행 또는 리포트에 연결된 등록이다. (FACE_REGISTRATION_IN_USE)")
  @ApiResponse(responseCode = "503", description = "사진 삭제가 끝나지 않아 재시도가 필요하다. (SERVICE_UNAVAILABLE)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.NotFound
  @DeleteMapping("/{faceRegistrationId}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void delete(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest servletRequest,
      @PathVariable UUID faceRegistrationId) {
    registrations.delete(principal.userId(), sessionId(servletRequest), faceRegistrationId);
  }

  private String sessionId(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session == null) {
      throw new BusinessException(ErrorCode.UNAUTHORIZED);
    }
    return session.getId();
  }
}
