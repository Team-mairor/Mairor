package com.mairor.backend.users;

import com.mairor.backend.users.dto.request.SignUpRequest;
import com.mairor.backend.users.dto.request.SignupAgreement;
import java.util.List;

/** 테스트용 가입 요청 생성기. 기본 요청은 선택 필드를 비우고 필수 약관 3종에 현재 버전으로 동의한다. */
public final class SignUpRequests {

  /** {@code application.yml} 의 약관 현재 버전 기본값. */
  public static final String CURRENT_VERSION = "2026-10-26";

  /** 요청 본문(JSON)에 넣는 필수 약관 3종 동의 + 마케팅 거부. */
  public static final String AGREEMENTS_JSON =
      """
      [{"type": "TERMS", "version": "2026-10-26", "agreed": true},
       {"type": "PRIVACY", "version": "2026-10-26", "agreed": true},
       {"type": "AGE_OVER_14", "version": "2026-10-26", "agreed": true},
       {"type": "MARKETING", "version": "2026-10-26", "agreed": false}]""";

  private SignUpRequests() {}

  public static List<SignupAgreement> requiredAgreements() {
    return List.of(
        new SignupAgreement("TERMS", CURRENT_VERSION, true),
        new SignupAgreement("PRIVACY", CURRENT_VERSION, true),
        new SignupAgreement("AGE_OVER_14", CURRENT_VERSION, true));
  }

  public static SignUpRequest basic(String email, String password, String passwordConfirm) {
    return withAgreements(email, password, passwordConfirm, requiredAgreements());
  }

  public static SignUpRequest withAgreements(
      String email, String password, String passwordConfirm, List<SignupAgreement> agreements) {
    return new SignUpRequest(
        email, password, passwordConfirm, null, null, null, null, null, agreements, null);
  }

  /** 필수 약관에 동의하고 이메일 인증 토큰을 실은 요청. */
  public static SignUpRequest withToken(
      String email, String password, String passwordConfirm, String token) {
    return new SignUpRequest(
        email,
        password,
        passwordConfirm,
        null,
        null,
        null,
        null,
        null,
        requiredAgreements(),
        token);
  }
}
