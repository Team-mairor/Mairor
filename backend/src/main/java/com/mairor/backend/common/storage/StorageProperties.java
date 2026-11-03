package com.mairor.backend.common.storage;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 객체 저장소 설정 ({@code app.storage}).
 *
 * @param type {@code local}(기본, 개발·테스트) 또는 {@code s3}(운영)
 * @param local 로컬 폴더 저장소의 뿌리 폴더. 키가 이 아래 상대 경로가 된다
 * @param s3 S3 버킷·리전. 자격 증명은 AWS 기본 공급자 체인(운영은 EC2 역할)이다
 */
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
    @DefaultValue("local") Type type, @DefaultValue Local local, @DefaultValue S3 s3) {

  public enum Type {
    LOCAL,
    S3
  }

  public record Local(@DefaultValue("${java.io.tmpdir}/mairor-storage") Path root) {}

  public record S3(String bucket, @DefaultValue("ap-northeast-2") String region) {}
}
