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
 * 운영자 가이드 검수. 검수 대기(PENDING) 가이드만 승인·반려한다. 같은 영상의 공개 가이드는 하나라({@code uk_guides_video_approved}) 새
 * 판을 승인하면 이전 공개 판은 반려(REJECTED)로 내린다.
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

  @Transactional(readOnly = true)
  public GuideView get(UUID guideId) {
    return GuideView.of(load(guideId));
  }

  /**
   * @throws BusinessException NOT_FOUND(없는 가이드), CONFLICT(검수 대기가 아님)
   */
  @Transactional
  public GuideView review(UUID guideId, Decision decision) {
    Guide guide = load(guideId);
    if (guide.getReviewStatus() != ReviewStatus.PENDING) {
      throw new BusinessException(
          ErrorCode.CONFLICT, "검수 대기(PENDING) 가이드만 검수할 수 있습니다. 지금 " + guide.getReviewStatus());
    }
    Instant now = clock.instant();
    if (decision == Decision.APPROVED) {
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
    } else {
      guide.reject(now);
    }
    notifier.changed(guide.getAnalysisJob().getId());
    log.info(
        "가이드 검수 guideId={} version={} decision={}", guide.getId(), guide.getVersion(), decision);
    return GuideView.of(guide);
  }

  private Guide load(UUID guideId) {
    return guides.findById(guideId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
  }
}
