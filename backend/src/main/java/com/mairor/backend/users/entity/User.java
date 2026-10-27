package com.mairor.backend.users.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;
import java.util.UUID;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 서비스 회원. 자체 가입 회원은 정규화한 이메일과 비밀번호 해시를 갖는다.
 *
 * <p>비밀번호 해시는 Google 로그인 전용 회원을 위해 비어 있을 수 있다. 이메일 유니크 제약의 이름({@value #EMAIL_UNIQUE})은 가입 처리에서 중복
 * 가입과 다른 제약 위반을 구분하는 데 쓴다.
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

  @CreationTimestamp
  @Column(name = "created_at", nullable = false, updatable = false)
  private Instant createdAt;

  @UpdateTimestamp
  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  protected User() {}

  public User(String email, String passwordHash) {
    this.email = email;
    this.passwordHash = passwordHash;
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

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }
}
