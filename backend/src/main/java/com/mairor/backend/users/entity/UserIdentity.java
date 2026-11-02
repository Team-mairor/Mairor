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
import org.hibernate.annotations.CreationTimestamp;

/**
 * 외부 로그인 제공자 계정과 회원의 연결. 지금은 Google 만 쓰고, {@code providerSubject} 는 ID 토큰의 {@code sub} 다. 이메일은 제공자
 * 쪽에서 바뀔 수 있어 계정을 찾는 데 쓰지 않는다. 제공자 계정 하나는 회원 하나에만 연결된다({@value #PROVIDER_SUBJECT_UNIQUE}). 제약 이름은
 * {@code db/schema/users.sql}과 같아야 한다.
 */
@Entity
@Table(
    name = "user_identities",
    uniqueConstraints =
        @UniqueConstraint(
            name = UserIdentity.PROVIDER_SUBJECT_UNIQUE,
            columnNames = {"provider", "provider_subject"}))
public class UserIdentity {

  public static final String PROVIDER_SUBJECT_UNIQUE = "uk_user_identities_provider_subject";
  public static final String USER_FK = "fk_user_identities_user";

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "user_id", nullable = false, foreignKey = @ForeignKey(name = USER_FK))
  private User user;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 10)
  private AuthProvider provider;

  @Column(name = "provider_subject", nullable = false, length = 255)
  private String providerSubject;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  protected UserIdentity() {}

  public UserIdentity(User user, AuthProvider provider, String providerSubject) {
    this.user = user;
    this.provider = provider;
    this.providerSubject = providerSubject;
  }

  public UUID getId() {
    return id;
  }

  public User getUser() {
    return user;
  }

  public AuthProvider getProvider() {
    return provider;
  }

  public String getProviderSubject() {
    return providerSubject;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
