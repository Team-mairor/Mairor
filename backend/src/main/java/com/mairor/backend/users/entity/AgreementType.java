package com.mairor.backend.users.entity;

/** 가입 때 받는 약관 종류. 필수 약관에 동의하지 않으면 가입할 수 없다. */
public enum AgreementType {
  /** 서비스 이용약관 */
  TERMS(true),
  /** 개인정보 수집·이용 */
  PRIVACY(true),
  /** 만 14세 이상 확인 */
  AGE_OVER_14(true),
  /** 마케팅 정보 수신 (선택) */
  MARKETING(false);

  private final boolean required;

  AgreementType(boolean required) {
    this.required = required;
  }

  public boolean required() {
    return required;
  }
}
