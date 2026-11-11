package com.mairor.backend.photos.controller;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.executions.service.ExecutionPhotoService;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "사진", description = "본인 실행에 연결된 비공개 사진을 조회한다.")
@RestController
@RequestMapping("/v1/users/me/photos")
public class PhotoContentController {
  private final ExecutionPhotoService photos;

  public PhotoContentController(ExecutionPhotoService photos) {
    this.photos = photos;
  }

  @Operation(
      summary = "사진 바이너리 조회",
      description = "권한이 확인된 본인 얼굴 등록 또는 실행 단계 사진 원본을 반환한다.",
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(responseCode = "200", description = "JPEG 또는 PNG 원본 이미지. Cache-Control: no-store.")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.NotFound
  @GetMapping(
      value = "/{photoId}",
      produces = {"image/jpeg", "image/png"})
  public ResponseEntity<byte[]> get(
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest request,
      @PathVariable UUID photoId) {
    var session = request.getSession(false);
    if (session == null) throw new BusinessException(ErrorCode.UNAUTHORIZED);
    var content = photos.get(principal.userId(), session.getId(), photoId);
    return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType(content.contentType()))
        .contentLength(content.bytes().length)
        .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
        .header("X-Content-Type-Options", "nosniff")
        .body(content.bytes());
  }
}
