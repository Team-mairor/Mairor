package com.mairor.backend.analysis.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

/**
 * 분석 작업 접수. 같은 영상의 진행 중 작업은 하나뿐이고(DB 부분 유일 인덱스), 동시에 두 요청이 같은 영상을 넣으면 한쪽은 새 작업, 다른 쪽은 그 작업에
 * 합류한다(API 명세 v2 API-VIDEO-002 "중복 생성하지 않는다").
 *
 * <p>저장소에 이미 있는 영상 파일로 작업을 바로 넣는다. 운영자 등록 API 는 지웠고(S15P31A306-409, 회원 분석 요청은 {@link
 * AnalysisRequestService}), 지금은 worker · 노트북 흐름 테스트가 작업을 만드는 데 쓴다.
 */
@Service
public class AnalysisJobService {

  private static final Logger log = LoggerFactory.getLogger(AnalysisJobService.class);

  private final AnalysisJobWriter writer;

  AnalysisJobService(AnalysisJobWriter writer) {
    this.writer = writer;
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
}
