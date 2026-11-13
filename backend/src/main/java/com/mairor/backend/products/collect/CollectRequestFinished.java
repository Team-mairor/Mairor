package com.mairor.backend.products.collect;

import com.mairor.backend.products.entity.CollectRequestStatus;
import java.util.UUID;

/**
 * 수집 요청이 끝났다. 커밋된 뒤 해결된 요청의 파우치 항목을 카탈로그에 연결하고(S15P31A306-517), 영상 분석 요청은 가이드 단계를 다시 대조한다
 * (S15P31A306-518).
 */
public record CollectRequestFinished(UUID requestId, CollectRequestStatus status) {}
