package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 분석 작업 접수·조회. 같은 영상의 진행 중 작업은 하나뿐이고(DB 부분 유일 인덱스), 동시에 두 요청이 같은 영상을 넣으면 한쪽은 새 작업, 다른 쪽은 그 작업에
 * 합류한다(API 명세 v2 API-VIDEO-002 "중복 생성하지 않는다").
 */
@Service
public class AnalysisJobService {

  private static final Logger log = LoggerFactory.getLogger(AnalysisJobService.class);

  private final AnalysisJobWriter writer;
  private final AnalysisJobRepository jobs;

  AnalysisJobService(AnalysisJobWriter writer, AnalysisJobRepository jobs) {
    this.writer = writer;
    this.jobs = jobs;
  }

  /**
   * 작업을 접수한다. 유일 제약 충돌(동시 요청)이면 새 트랜잭션으로 한 번 더 시도해 먼저 만들어진 영상·작업을 읽는다.
   *
   * @throws IllegalArgumentException 영상 파일 키가 형식에 맞지 않으면
   */
  public AnalysisJobReceipt register(AnalysisJobRequest request) {
    AnalysisJobReceipt receipt;
    try {
      receipt = writer.register(request);
    } catch (DataIntegrityViolationException conflict) {
      log.info("분석 작업 접수가 동시 요청과 겹쳐 다시 읽습니다. youtubeVideoId={}", request.youtubeVideoId());
      receipt = writer.register(request);
    }
    log.info(
        "분석 작업 접수 jobId={} videoId={} receipt={}",
        receipt.jobId(),
        receipt.videoId(),
        receipt.receiptType());
    return receipt;
  }

  /**
   * @throws BusinessException 404 {@code NOT_FOUND} — 없는 작업
   */
  @Transactional(readOnly = true)
  public AnalysisJobView get(UUID jobId) {
    AnalysisJob job =
        jobs.findById(jobId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    return AnalysisJobView.of(job);
  }
}
