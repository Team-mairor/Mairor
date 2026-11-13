package com.mairor.backend.pouch.event;

import java.util.UUID;

/**
 * 회원이 카탈로그에 없는 제품을 직접 입력(MANUAL)으로 파우치에 등록했다. 등록이 커밋된 뒤 수집 요청을 만드는 데 쓴다.
 *
 * @param userId 등록한 회원
 * @param pouchItemId 등록된 파우치 항목
 */
public record PouchItemRegisteredManually(UUID userId, UUID pouchItemId) {}
