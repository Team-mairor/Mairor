package com.mairor.backend.common.storage;

import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;

/**
 * 객체 저장소. 운영은 S3({@link S3ObjectStorage}), 개발·테스트는 로컬 폴더({@link LocalObjectStorage})다. 설정 {@code
 * app.storage.type}으로 고른다.
 *
 * <p>키는 {@code videos/{youtubeVideoId}/source.mp4}처럼 {@code /}로 나눈 상대 경로다.
 */
public interface ObjectStorage {

  /**
   * 객체를 파일로 내려받는다. 대상 파일이 있으면 덮어쓴다.
   *
   * @throws ObjectNotFoundException 키에 객체가 없으면
   * @throws StorageException 저장소에 닿지 못하면(일시적일 수 있다)
   */
  void download(String key, Path target);

  /**
   * @throws StorageException 저장소에 닿지 못하면
   */
  boolean exists(String key);

  /**
   * 파일을 키로 올린다. 같은 키가 있으면 덮어쓴다.
   *
   * @throws StorageException 저장소에 닿지 못하면
   */
  void upload(Path source, String key, String contentType);

  /**
   * 로그인 없이 내려받을 수 있는 주소. S3 는 사전 서명 URL, 로컬은 {@code file:} URI 다.
   *
   * <p>S3 사전 서명 URL 은 서명한 자격 증명이 끝나면 함께 끝난다. 운영 EC2 는 역할의 임시 자격 증명(몇 시간마다 바뀜)이라 {@code ttl}보다 일찍 끝날
   * 수 있으므로, 받는 쪽은 받은 뒤 바로 내려받는다.
   *
   * @throws StorageException 주소를 만들지 못하면
   */
  URI presignGet(String key, Duration ttl);
}
