package com.mairor.backend.guides.service;

import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 가이드를 열 때, 카탈로그가 나중에 채워졌으면 이어질 수 있는 단계가 남아 있는지 보고 원본 제품 대조를 비동기로 다시 예약한다.
 *
 * <p>대조는 분석 직후와 수집 요청이 끝난 뒤에만 돌기 때문에, 앱을 거치지 않고 카탈로그에 넣은 제품은 이미 저장된 가이드에 이어지지 않는다. 연결이 영영 안 되는 제품
 * 때문에 열 때마다 되풀이하지 않도록 같은 가이드는 {@link #MIN_INTERVAL}에 한 번만 예약한다. 대조는 사용자를 기다리게 하지 않는다.
 *
 * <p>가이드 조회 API에서만 부른다. 실행 시작처럼 이미 만든 매칭을 쓰는 경로에서 대조가 돌면 reference_version이 올라 그 매칭이 낡아진다.
 */
@Component
public class GuideReferenceLinkRefresher {

  public static final Duration MIN_INTERVAL = Duration.ofMinutes(10);

  /** 카탈로그가 채워지면 달라질 수 있는 사유. 영상에 제품·호수 정보가 없거나 지원하지 않는 종류는 다시 대조해도 같다. */
  private static final Set<ReferenceMatchReason> RETRYABLE =
      EnumSet.of(
          ReferenceMatchReason.PRODUCT_NOT_FOUND,
          ReferenceMatchReason.PRODUCT_AMBIGUOUS,
          ReferenceMatchReason.SHADE_NOT_FOUND,
          ReferenceMatchReason.SHADE_AMBIGUOUS,
          ReferenceMatchReason.NO_COLOR_SLOTS,
          ReferenceMatchReason.SLOT_UNIDENTIFIED);

  private static final Logger log = LoggerFactory.getLogger(GuideReferenceLinkRefresher.class);

  private final GuideRepository guides;
  private final GuideStepProductLinkRepository productLinks;
  private final GuideReferenceLinkReconciliationDispatcher dispatcher;
  private final ObjectMapper objectMapper;
  private final Clock clock;
  private final Map<UUID, Instant> lastScheduled = new ConcurrentHashMap<>();

  GuideReferenceLinkRefresher(
      GuideRepository guides,
      GuideStepProductLinkRepository productLinks,
      GuideReferenceLinkReconciliationDispatcher dispatcher,
      ObjectMapper objectMapper,
      Clock clock) {
    this.guides = guides;
    this.productLinks = productLinks;
    this.dispatcher = dispatcher;
    this.objectMapper = objectMapper;
    this.clock = clock;
  }

  /** 가이드 조회 응답을 막지 않는다. 최근에 예약했으면 DB도 읽지 않고 돌아간다. */
  @Transactional(readOnly = true)
  public void refreshIfNeeded(UUID guideId) {
    try {
      Instant last = lastScheduled.get(guideId);
      if (last != null && last.plus(MIN_INTERVAL).isAfter(clock.instant())) {
        return;
      }
      var guide = guides.findById(guideId).orElse(null);
      if (guide == null) {
        return;
      }
      List<String> stepIds = new ArrayList<>();
      JsonNode steps = objectMapper.readTree(guide.getGuideInput()).path("steps");
      for (JsonNode step : steps) {
        stepIds.add(step.path("stepId").asString(""));
      }
      Map<String, GuideStepProductLink> links = new HashMap<>();
      for (GuideStepProductLink link : productLinks.findByGuideIdOrderByStepIdAsc(guideId)) {
        links.put(link.getStepId(), link);
      }
      refreshIfNeeded(guideId, stepIds, links);
    } catch (RuntimeException e) {
      log.warn("가이드 원본 제품 재대조 예약 확인 실패 guideId={}", guideId, e);
    }
  }

  /**
   * @param stepIds 가이드 입력의 모든 단계 ID
   * @param links 이미 저장된 단계 연결
   */
  void refreshIfNeeded(
      UUID guideId, Collection<String> stepIds, Map<String, GuideStepProductLink> links) {
    if (!hasStepThatCouldLinkMore(stepIds, links) || !claimSlot(guideId)) {
      return;
    }
    dispatcher.scheduleAfterCommit(guideId);
  }

  private static boolean hasStepThatCouldLinkMore(
      Collection<String> stepIds, Map<String, GuideStepProductLink> links) {
    for (String stepId : stepIds) {
      GuideStepProductLink link = links.get(stepId);
      if (link == null) {
        return true;
      }
      if (link.getMatchLevel() != ReferenceMatchLevel.SLOT
          && link.getReasonCode() != null
          && RETRYABLE.contains(link.getReasonCode())) {
        return true;
      }
    }
    return false;
  }

  /** 마지막 예약 뒤 {@link #MIN_INTERVAL}이 지났을 때만 자리를 얻는다. 동시에 들어와도 한 번만 얻는다. */
  private boolean claimSlot(UUID guideId) {
    Instant now = clock.instant();
    boolean[] claimed = {false};
    lastScheduled.compute(
        guideId,
        (id, last) -> {
          if (last == null || !last.plus(MIN_INTERVAL).isAfter(now)) {
            claimed[0] = true;
            return now;
          }
          return last;
        });
    return claimed[0];
  }
}
