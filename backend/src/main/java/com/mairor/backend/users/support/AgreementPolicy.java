package com.mairor.backend.users.support;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.users.dto.request.SignupAgreement;
import com.mairor.backend.users.entity.AgreementType;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/**
 * 가입 약관 규칙. 필수 약관(이용약관·개인정보·만 14세 이상)이 모두 있고 {@code agreed=true}이며 버전이 서버의 현재 버전과 같아야 한다. 마케팅(선택)은
 * 있으면 그대로 기록한다.
 *
 * <p>같은 종류가 두 번 오면 {@code VALIDATION_FAILED}, 필수 약관이 비었거나 동의하지 않았거나 버전이 다르면 {@code
 * USERS_REQUIRED_AGREEMENT_MISSING}(400, {@code details[].field}는 {@code agreements.TERMS} 등)이다.
 */
@Component
public class AgreementPolicy {

  public static final String REQUIRED_AGREEMENT_MISSING = "USERS_REQUIRED_AGREEMENT_MISSING";

  private final AgreementProperties properties;

  public AgreementPolicy(AgreementProperties properties) {
    this.properties = properties;
  }

  /** 규칙을 어기면 예외를 던지고, 통과하면 종류별로 모은 동의 기록을 돌려준다. */
  public Map<AgreementType, SignupAgreement> validate(List<SignupAgreement> agreements) {
    Map<AgreementType, SignupAgreement> byType = new EnumMap<>(AgreementType.class);
    for (SignupAgreement agreement : agreements) {
      if (byType.put(AgreementType.valueOf(agreement.type()), agreement) != null) {
        throw validationFailed("agreements", "같은 약관 종류가 중복되었습니다: " + agreement.type());
      }
    }

    List<ErrorResponse.FieldError> missing = new ArrayList<>();
    for (AgreementType type : AgreementType.values()) {
      if (!type.required()) {
        continue;
      }
      String reason = problem(type, byType.get(type));
      if (reason != null) {
        missing.add(new ErrorResponse.FieldError("agreements." + type.name(), reason));
      }
    }
    if (!missing.isEmpty()) {
      throw new BusinessException(
          HttpStatus.BAD_REQUEST,
          REQUIRED_AGREEMENT_MISSING,
          "필수 약관에 모두 동의해야 가입할 수 있습니다.",
          missing,
          null);
    }
    return byType;
  }

  private String problem(AgreementType type, SignupAgreement agreement) {
    if (agreement == null) {
      return "필수 약관 동의 정보가 없습니다.";
    }
    if (!Boolean.TRUE.equals(agreement.agreed())) {
      return "필수 약관에 동의해야 합니다.";
    }
    if (!properties.currentVersion(type).equals(agreement.version())) {
      return "약관 버전이 최신이 아닙니다.";
    }
    return null;
  }

  private static BusinessException validationFailed(String field, String reason) {
    return new BusinessException(
        HttpStatus.BAD_REQUEST,
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError(field, reason)),
        null);
  }
}
