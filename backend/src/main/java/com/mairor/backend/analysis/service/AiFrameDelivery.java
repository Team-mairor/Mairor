package com.mairor.backend.analysis.service;

import com.mairor.backend.common.external.ai.AiProperties;
import com.mairor.backend.common.storage.ObjectStorage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * AI 가이드 요청에 레퍼런스 프레임을 싣는가. 요청을 만들 때(BUILDING_GUIDE) 한 번 정하고, 싣지 않으면 가이드의 프레임 목록 키를 비워 둔다. 콜백
 * 검사(프레임을 보낸 작업이면 영역이 있어야 한다)는 설정을 다시 보지 않고 그 기록을 읽으므로, 요청한 worker 와 콜백을 받는 api 의 설정이 달라도 어긋나지 않는다.
 *
 * <p>설정 {@code app.ai.send-frames}가 있으면 그 값, 비어 있으면 저장소가 AI 서버가 내려받을 수 있는 http 주소를 줄 때만 싣는다. 로컬
 * 저장소는 {@code file:} 주소라 AI 가 요청 전체를 거절하므로, 영역 없이 설명만 맡긴다.
 */
@Component
public class AiFrameDelivery {

  private static final Logger log = LoggerFactory.getLogger(AiFrameDelivery.class);

  private final boolean enabled;

  public AiFrameDelivery(AiProperties properties, ObjectStorage storage) {
    Boolean configured = properties.sendFrames();
    this.enabled = configured != null ? configured : storage.servesHttpUrls();
    if (!enabled) {
      log.info("AI 가이드 요청에 레퍼런스 프레임을 싣지 않음(영역 없이 설명만). 저장소 http 주소={}", storage.servesHttpUrls());
    }
  }

  /** 요청에 프레임을 싣는가. */
  public boolean enabled() {
    return enabled;
  }
}
