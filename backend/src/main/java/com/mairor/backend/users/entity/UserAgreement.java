package com.mairor.backend.users.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.UUID;

/**
 * 회원별 약관 동의 기록(종류·버전·동의 여부·동의 시각). 회원당 약관 종류별로 한 행이고({@value #USER_TYPE_UNIQUE}), 제약 이름은 {@code
 * db/schema/users.sql}과 같아야 한다.
 */
@Entity
@Table(
    name = "user_agreements",
    uniqueConstraints =
        @UniqueConstraint(
            name = UserAgreement.USER_TYPE_UNIQUE,
            columnNames = {"user_id", "type"}))
public class UserAgreement {

  public static final String USER_TYPE_UNIQUE = "uk_user_agreements_user_type";
  public static final String USER_FK = "fk_user_agreements_user";

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "user_id", nullable = false, foreignKey = @ForeignKey(name = USER_FK))
  private User user;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 30)
  private AgreementType type;

  @Column(nullable = false, length = 20)
  private String version;

  @Column(nullable = false)
  private boolean agreed;

  @Column(name = "agreed_at", nullable = false, updatable = false)
  private Instant agreedAt;

  protected UserAgreement() {}

  public UserAgreement(
      User user, AgreementType type, String version, boolean agreed, Instant agreedAt) {
    this.user = user;
    this.type = type;
    this.version = version;
    this.agreed = agreed;
    this.agreedAt = agreedAt;
  }

  public UUID getId() {
    return id;
  }

  public User getUser() {
    return user;
  }

  public AgreementType getType() {
    return type;
  }

  public String getVersion() {
    return version;
  }

  public boolean isAgreed() {
    return agreed;
  }

  public Instant getAgreedAt() {
    return agreedAt;
  }
}
