package com.mairor.backend.users.repository;

import com.mairor.backend.users.entity.UserAgreement;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserAgreementRepository extends JpaRepository<UserAgreement, UUID> {

  List<UserAgreement> findByUserId(UUID userId);
}
