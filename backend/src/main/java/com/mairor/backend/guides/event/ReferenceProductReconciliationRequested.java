package com.mairor.backend.guides.event;

import java.util.UUID;

/** 콜백 트랜잭션이 커밋된 뒤 레퍼런스 제품 연결을 시작한다. */
public record ReferenceProductReconciliationRequested(UUID guideId) {}
