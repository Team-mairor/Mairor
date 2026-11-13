package com.mairor.backend.products.collect;

import java.util.UUID;

/** 새 수집 요청을 QUEUED 로 넣었다. 커밋된 뒤 큐에 보낸다. */
public record CollectRequestQueued(UUID requestId) {}
