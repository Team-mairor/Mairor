package com.mairor.backend.guides.service;

import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.repository.GuideRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 가이드 공개와 내리기. AI 결과를 저장하면 검수 없이 바로 공개한다({@link #publish}, S15P31A306-409 · 11.12 팀 합의). 사람이 부르는 검수
 * API 는 없다(모두 자동). 같은 영상의 공개 가이드는 하나라({@code uk_guides_video_approved}) 새 판을 공개하면 이전 공개 판은
 * 반려(REJECTED)로 내린다.
 *
 * <p>검수 상태는 회원의 분석 상태에 보이므로, 바뀐 가이드마다 그 분석 작업을 {@link AnalysisJobNotifier}로 알린다.
 */
@Service
public class GuideReviewService {

  public enum Decision {
    APPROVED,
    REJECTED
  }

  private static final Logger log = LoggerFactory.getLogger(GuideReviewService.class);

  private final GuideRepository guides;
  private final AnalysisJobNotifier notifier;
  private final Clock clock;

  GuideReviewService(GuideRepository guides, AnalysisJobNotifier notifier, Clock clock) {
    this.guides = guides;
    this.notifier = notifier;
    this.clock = clock;
  }

  /**
   * 검수 결정. 승인은 검수 대기(PENDING) 가이드만(자동 공개 전에 만든 옛 작업), 반려는 검수 대기 · 공개 가이드 둘 다 받는다(공개 가이드면 내린다).
   *
   * @throws BusinessException NOT_FOUND(없는 가이드), CONFLICT(그 결정을 내릴 수 없는 상태)
   */
  @Transactional
  public GuideView review(UUID guideId, Decision decision) {
    Guide guide = load(guideId);
    ReviewStatus current = guide.getReviewStatus();
    Instant now = clock.instant();
    if (decision == Decision.APPROVED) {
      if (current != ReviewStatus.PENDING) {
        throw new BusinessException(
            ErrorCode.CONFLICT, "검수 대기(PENDING) 가이드만 승인할 수 있습니다. 지금 " + current);
      }
      publish(guide, now);
    } else {
      if (current != ReviewStatus.PENDING && current != ReviewStatus.APPROVED) {
        throw new BusinessException(
            ErrorCode.CONFLICT, "검수 대기(PENDING) · 공개(APPROVED) 가이드만 반려할 수 있습니다. 지금 " + current);
      }
      guide.reject(now);
    }
    notifier.changed(guide.getAnalysisJob().getId());
    log.info(
        "가이드 검수 guideId={} version={} {} → {}",
        guide.getId(),
        guide.getVersion(),
        current,
        guide.getReviewStatus());
    return GuideView.of(guide);
  }

  /**
   * 검수 대기(PENDING) 가이드를 공개한다. 같은 영상의 이전 공개 판이 있으면 먼저 내리고 그 분석 작업에 알린다. 이 가이드의 분석 작업 알림은 부르는 쪽이
   * 한다(작업 상태도 같이 바꾸므로). 부르는 쪽 트랜잭션 안에서 쓴다.
   */
  @Transactional
  public void publish(Guide guide, Instant now) {
    guides
        .findByVideoIdAndReviewStatus(guide.getVideo().getId(), ReviewStatus.APPROVED)
        .ifPresent(
            previous -> {
              previous.supersede(now);
              // 새 판을 APPROVED 로 바꾸기 전에 내려야 공개 하나 제약(부분 유일 인덱스)에 걸리지 않는다
              guides.saveAndFlush(previous);
              notifier.changed(previous.getAnalysisJob().getId());
              log.info(
                  "이전 공개 가이드 내림 guideId={} version={}", previous.getId(), previous.getVersion());
            });
    guide.approve(now);
  }

  private Guide load(UUID guideId) {
    return guides.findById(guideId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
  }
}
