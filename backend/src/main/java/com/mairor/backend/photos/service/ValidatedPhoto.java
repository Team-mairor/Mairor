package com.mairor.backend.photos.service;

import java.nio.file.Path;

/** 파일 검증부터 업로드까지 쓰는 서버 임시 파일. 요청 종료 전에 반드시 닫는다. */
public record ValidatedPhoto(
    Path path,
    String contentType,
    long byteSize,
    int width,
    int height,
    PhotoTemporaryFiles.Lease lease)
    implements AutoCloseable {
  @Override
  public void close() {
    lease.close();
  }
}
