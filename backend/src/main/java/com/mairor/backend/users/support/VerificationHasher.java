package com.mairor.backend.users.support;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/**
 * 인증번호와 인증 토큰을 저장소에 넣기 전에 해시해서, 저장소가 유출돼도 평문을 알 수 없게 한다.
 *
 * <p>인증번호는 6자리 숫자라 그냥 해시하면 바로 역산되므로, 서버만 아는 비밀키로 HMAC-SHA256 을 쓰고 이메일도 함께 묶는다. 저장소가 같은 입력에 같은 값을 받아
 * 원자적으로 비교해야 해서 bcrypt 같은 느린 해시는 쓰지 않는다. 토큰은 충분히 긴 난수라 SHA-256 이면 된다.
 *
 * <p>비밀키({@code app.email-verification.secret})가 비어 있으면 기동할 때마다 임의로 만든다. 서버가 여러 대이면 같은 값을 설정해야 한다.
 */
@Component
public class VerificationHasher {

  private static final Logger log = LoggerFactory.getLogger(VerificationHasher.class);
  private static final String HMAC = "HmacSHA256";

  private final byte[] secret;

  @Autowired
  public VerificationHasher(EmailVerificationProperties properties) {
    this(properties.secret());
  }

  VerificationHasher(String secret) {
    if (StringUtils.hasText(secret)) {
      this.secret = secret.getBytes(StandardCharsets.UTF_8);
    } else {
      log.warn(
          "EMAIL_VERIFICATION_SECRET 이 비어 있어 임시 비밀키를 만들었습니다. 재시작하면 진행 중인 인증이 무효가 됩니다. "
              + "서버를 여러 대 두거나 Redis 를 쓰기 전에 반드시 설정하세요.");
      this.secret = new byte[32];
      new SecureRandom().nextBytes(this.secret);
    }
  }

  /** 인증번호 해시. 이메일과 묶어서 계산한다. */
  public String hashCode(String email, String code) {
    try {
      Mac mac = Mac.getInstance(HMAC);
      mac.init(new SecretKeySpec(secret, HMAC));
      // 이메일 길이를 앞에 붙여 이메일과 코드의 경계가 달라도 같은 문자열이 되지 않게 한다
      byte[] digest =
          mac.doFinal(
              ("code:" + email.length() + ":" + email + ":" + code)
                  .getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(digest);
    } catch (GeneralSecurityException e) {
      throw new IllegalStateException("인증번호 해시를 계산할 수 없습니다.", e);
    }
  }

  /** 인증 토큰 해시 (SHA-256). */
  public String hashToken(String token) {
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(digest);
    } catch (GeneralSecurityException e) {
      throw new IllegalStateException("토큰 해시를 계산할 수 없습니다.", e);
    }
  }
}
