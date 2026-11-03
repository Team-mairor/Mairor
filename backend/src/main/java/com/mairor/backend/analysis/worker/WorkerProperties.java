package com.mairor.backend.analysis.worker;

import java.nio.file.Path;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 분석 worker 설정 ({@code app.analysis.worker}).
 *
 * @param pollInterval 대기 작업을 확인하는 간격
 * @param workDir 작업마다 영상·프레임을 잠깐 두는 폴더. 작업이 끝나면 작업별 하위 폴더를 지운다
 * @param ffprobePath ffprobe 실행 파일
 * @param ffprobeTimeout ffprobe 한 번의 시간 제한
 */
@ConfigurationProperties(prefix = "app.analysis.worker")
public record WorkerProperties(
    @DefaultValue("5s") Duration pollInterval,
    @DefaultValue("${java.io.tmpdir}/mairor-analysis") Path workDir,
    @DefaultValue("ffprobe") String ffprobePath,
    @DefaultValue("60s") Duration ffprobeTimeout) {}
