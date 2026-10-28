package com.mairor.backend.users.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 서비스 회원. 닉네임·이름·휴대폰·생년월일·성별은 가입 때 선택이라 비어 있을 수 있고, 비밀번호 해시는 Google 로그인 전용 회원을 위해 비어 있을 수 있다. 이메일
 * 유니크 제약의 이름({@value #EMAIL_UNIQUE})은 가입 처리에서 중복 가입과 다른 제약 위반을 구분하는 데 쓴다.
 */
@Entity
@Table(
    name = "users",
    uniqueConstraints = @UniqueConstraint(name = User.EMAIL_UNIQUE, columnNames = "email"))
public class User {

  public static final String EMAIL_UNIQUE = "uk_users_email";

  @Id
  @GeneratedValue(strategy = GenerationType.UUID)
  private UUID id;

  @Column(nullable = false, length = 254)
  private String email;

  @Column(name = "password_hash", length = 255)
  private String passwordHash;

  @Enumerated(EnumType.STRING)
  @Column(nullable = false, length = 10)
  private AuthProvider provider;

  @Column(length = 20)
  private String nickname;

  @Column(length = 50)
  private String name;

  @Column(length = 11)
  private String phone;

  @Column(name = "birth_date")
  private LocalDate birthDate;

  @Enumerated(EnumType.STRING)
  @Column(length = 10)
  private Gender gender;

  /** 이메일 인증 토큰으로 소유를 확인하고 가입한 시각. 인증 없이 가입했으면 {@code null}. */
  @Column(name = "email_verified_at")
  private Instant emailVerifiedAt;

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected User() {}

  /** 프로필 없이 이메일·비밀번호 해시만 가진 자체 가입 회원. */
  public User(String email, String passwordHash) {
    this(email, passwordHash, AuthProvider.LOCAL, null, null, null, null, null, null);
  }

  public User(
      String email,
      String passwordHash,
      AuthProvider provider,
      String nickname,
      String name,
      String phone,
      LocalDate birthDate,
      Gender gender,
      Instant emailVerifiedAt) {
    this.email = email;
    this.passwordHash = passwordHash;
    this.provider = provider;
    this.nickname = nickname;
    this.name = name;
    this.phone = phone;
    this.birthDate = birthDate;
    this.gender = gender;
    this.emailVerifiedAt = emailVerifiedAt;
  }

  public UUID getId() {
    return id;
  }

  public String getEmail() {
    return email;
  }

  public String getPasswordHash() {
    return passwordHash;
  }

  public AuthProvider getProvider() {
    return provider;
  }

  public String getNickname() {
    return nickname;
  }

  public String getName() {
    return name;
  }

  public String getPhone() {
    return phone;
  }

  public LocalDate getBirthDate() {
    return birthDate;
  }

  public Gender getGender() {
    return gender;
  }

  public Instant getEmailVerifiedAt() {
    return emailVerifiedAt;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
