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
 * @param resultDir 수집기가 쓴 실행 결과 파일(JSONL)이 있는 폴더. ai·api·worker 컨테이너가 같이 마운트한 공유 볼륨이다. 서버는 읽기만 한다.
 *     파일을 읽어 적재하는 API 와 근거 조회가 이 폴더 안의 파일만 연다
 */
@ConfigurationProperties(prefix = "catalog.import")
public record CatalogImportProperties(
    @DefaultValue("10m") Duration heartbeatTimeout,
    @DefaultValue("/data/catalog-runs") Path resultDir) {}
