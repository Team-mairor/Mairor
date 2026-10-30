package com.mairor.backend.users;

import com.mairor.backend.common.mail.AuthMailSender;
import com.mairor.backend.common.mail.MailDeliveryException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

/**
 * 이메일 인증을 다루는 통합 테스트가 같이 쓰는 도구. 실제 메일 대신 보낸 메일을 모아 두는 발송기와, 테스트가 움직일 수 있는 시계를 {@link TestBeans}로
 * 컨텍스트에 끼워 넣는다. 쿨다운·만료를 실제로 기다리지 않고 확인하기 위해서다.
 */
public final class VerificationTestSupport {

  public static final Instant T0 = Instant.parse("2026-10-27T00:00:00Z");

  private VerificationTestSupport() {}

  /**
   * 보낸 메일을 종류별로 모아 두고, 원하면 실패시키는 발송기. 가입 인증번호는 {@link #sent}, 비밀번호 재설정 인증번호는 {@link #resetCodes},
   * Google 전용 계정 안내는 {@link #googleNotices}에 쌓인다. {@code failing} 은 모든 종류에 적용된다.
   */
  public static class CapturingMailSender implements AuthMailSender {

    public record Mail(String to, String code, Duration validFor) {}

    public final List<Mail> sent = new CopyOnWriteArrayList<>();
    public final List<Mail> resetCodes = new CopyOnWriteArrayList<>();
    public final List<String> googleNotices = new CopyOnWriteArrayList<>();
    public volatile boolean failing;

    @Override
    public void send(String to, String code, Duration validFor) {
      failIfAsked();
      sent.add(new Mail(to, code, validFor));
    }

    @Override
    public void sendResetCode(String to, String code, Duration validFor) {
      failIfAsked();
      resetCodes.add(new Mail(to, code, validFor));
    }

    @Override
    public void sendGoogleAccountNotice(String to) {
      failIfAsked();
      googleNotices.add(to);
    }

    public Mail last() {
      return sent.get(sent.size() - 1);
    }

    public Mail lastResetCode() {
      return resetCodes.get(resetCodes.size() - 1);
    }

    private void failIfAsked() {
      if (failing) {
        throw new MailDeliveryException("test failure");
      }
    }
  }

  /** 테스트가 시각을 정하는 시계. */
  public static class MutableClock extends Clock {

    private final AtomicReference<Instant> now = new AtomicReference<>(T0);

    public void set(Instant instant) {
      now.set(instant);
    }

    public void advance(Duration duration) {
      now.updateAndGet(i -> i.plus(duration));
    }

    @Override
    public ZoneId getZone() {
      return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
      return this;
    }

    @Override
    public Instant instant() {
      return now.get();
    }
  }

  @TestConfiguration
  public static class TestBeans {

    @Bean
    @Primary
    CapturingMailSender capturingMailSender() {
      return new CapturingMailSender();
    }

    @Bean
    @Primary
    MutableClock mutableClock() {
      return new MutableClock();
    }
  }
}
