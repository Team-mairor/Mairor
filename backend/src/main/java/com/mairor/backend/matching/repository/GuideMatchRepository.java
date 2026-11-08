package com.mairor.backend.matching.repository;

import com.mairor.backend.matching.entity.GuideMatch;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/** 매칭 ID와 회원 ID를 함께 검사해 다른 회원의 결과 스냅샷을 읽지 않는다. */
public interface GuideMatchRepository extends JpaRepository<GuideMatch, UUID> {

  Optional<GuideMatch> findByIdAndUserId(UUID id, UUID userId);
}
