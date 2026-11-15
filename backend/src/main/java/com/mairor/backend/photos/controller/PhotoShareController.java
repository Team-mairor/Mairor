package com.mairor.backend.photos.controller;

import com.mairor.backend.executions.service.ExecutionPhotoService;
import com.mairor.backend.photos.dto.PhotoShareResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Tag(name = "사진", description = "네컷 사진 QR 공유를 만들고 공유 사진을 조회한다.")
@RestController
public class PhotoShareController {
  private final ExecutionPhotoService photos;

  public PhotoShareController(ExecutionPhotoService photos) {
    this.photos = photos;
  }

  @Operation(
      summary = "네컷 사진 QR 공유 만들기",
      description = "JPEG 네컷 사진을 올리면 로그인 없이 열 수 있는 만료 공유 ID를 반환한다.")
  @PostMapping(
      value = "/v1/photo-shares",
      consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
      produces = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.CREATED)
  public PhotoShareResponse create(@RequestPart("image") MultipartFile image) {
    return photos.createShare(image);
  }

  @Operation(summary = "QR 공유 네컷 사진 조회", description = "공유 ID가 유효한 동안 인증 없이 사진 원본을 반환한다.")
  @GetMapping(
      value = "/v1/photo-shares/{shareId}",
      produces = {"image/jpeg", "image/png"})
  public ResponseEntity<byte[]> getShared(@PathVariable UUID shareId) {
    var content = photos.getShared(shareId);
    return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType(content.contentType()))
        .contentLength(content.bytes().length)
        .header(HttpHeaders.CACHE_CONTROL, "no-store")
        .header("X-Content-Type-Options", "nosniff")
        .body(content.bytes());
  }
}
