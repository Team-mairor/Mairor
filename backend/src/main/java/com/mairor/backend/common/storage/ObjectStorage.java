package com.mairor.backend.common.storage;

import java.nio.file.Path;

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
}
