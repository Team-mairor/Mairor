package com.mairor.backend.products.imports;

import java.nio.file.Path;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 카탈로그 적재 실행 설정({@code catalog.import}).
 *
 * @param heartbeatTimeout 진행 중인 실행에서 이 시간 동안 하트비트(건 전송 포함)가 없으면 서버가 {@code ABANDONED}로 끝낸다. 수집기는
 *     5분마다 하트비트를 보내므로 그 두 배 이상으로 둔다
 * @param resultDir 실행 결과 파일(JSONL)을 여는 폴더. {@code source=local}이면 수집기가 쓴 폴더 그 자체, {@code
 *     source=storage}면 저장소에서 받은 파일을 두는 캐시 폴더다. 파일을 읽어 적재하는 API 와 근거 조회가 이 폴더 안의 파일만 연다
 * @param source 결과 파일을 어디서 가져오나. {@code local}은 {@code resultDir}에 이미 있는 파일, {@code storage}는 객체
 *     저장소({@code app.storage})의 {@code storagePrefix} 아래 파일이다. 운영은 BE 와 수집기가 서버가 달라 {@code
 *     storage}다
 * @param storagePrefix 저장소에서 결과 파일이 있는 접두사. 키는 접두사 + 파일 이름이다
 * @param storageCacheTtl 저장소에서 받은 파일을 다시 받지 않고 쓰는 시간. 한 파일을 나눠 적재하는 동안 같은 파일을 매번 받지 않으려고 둔다
 */
@ConfigurationProperties(prefix = "catalog.import")
public record CatalogImportProperties(
    @DefaultValue("10m") Duration heartbeatTimeout,
    @DefaultValue("/data/catalog-runs") Path resultDir,
    @DefaultValue("local") Source source,
    @DefaultValue("catalog-runs/") String storagePrefix,
    @DefaultValue("5m") Duration storageCacheTtl) {

  /** 결과 파일을 가져오는 곳. */
  public enum Source {
    LOCAL,
    STORAGE
  }

  /** 로컬 폴더에서만 읽는 설정. 테스트와 개발용. */
  public static CatalogImportProperties local(Duration heartbeatTimeout, Path resultDir) {
    return new CatalogImportProperties(
        heartbeatTimeout, resultDir, Source.LOCAL, "catalog-runs/", Duration.ofMinutes(5));
  }
}
