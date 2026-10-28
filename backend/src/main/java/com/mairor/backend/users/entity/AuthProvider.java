package com.mairor.backend.users.entity;

/** 가입 경로. 자체 가입은 {@code LOCAL}, Google 로그인으로 만든 회원은 {@code GOOGLE}(S15P31A306-208). */
public enum AuthProvider {
  LOCAL,
  GOOGLE
}
