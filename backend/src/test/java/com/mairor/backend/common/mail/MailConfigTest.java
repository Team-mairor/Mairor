package com.mairor.backend.common.mail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.mail.autoconfigure.MailSenderAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

/** 설정에 따라 어떤 발송기가 만들어지는지, 잘못된 설정이 시작 단계에서 드러나는지 확인한다. */
class MailConfigTest {

  @Configuration
  @EnableConfigurationProperties(AppMailProperties.class)
  static class PropertiesConfig {}

  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withConfiguration(AutoConfigurations.of(MailSenderAutoConfiguration.class))
          .withUserConfiguration(PropertiesConfig.class, MailConfig.class)
          .withPropertyValues("spring.mail.host=smtp.example.com");

  @Test
  void disabledOutsideProd_usesTheLoggingSender() {
    runner
        .withPropertyValues("app.mail.enabled=false")
        .run(
            context ->
                assertThat(context.getBean(VerificationMailSender.class))
                    .isInstanceOf(LoggingVerificationMailSender.class));
  }

  @Test
  void notConfiguredAtAll_defaultsToTheLoggingSender() {
    runner.run(
        context ->
            assertThat(context.getBean(VerificationMailSender.class))
                .isInstanceOf(LoggingVerificationMailSender.class));
  }

  @Test
  void disabledInProd_usesTheSenderThatAlwaysFails_andNeverLogsTheCode() {
    runner
        .withInitializer(context -> context.getEnvironment().setActiveProfiles("prod"))
        .withPropertyValues("app.mail.enabled=false")
        .run(
            context -> {
              VerificationMailSender sender = context.getBean(VerificationMailSender.class);
              assertThat(sender).isInstanceOf(UnavailableVerificationMailSender.class);
              assertThatThrownBy(
                      () -> sender.send("member@example.com", "123456", Duration.ofMinutes(10)))
                  .isInstanceOf(MailDeliveryException.class);
              PasswordResetMailSender reset = context.getBean(PasswordResetMailSender.class);
              assertThatThrownBy(
                      () ->
                          reset.sendResetCode(
                              "member@example.com", "123456", Duration.ofMinutes(10)))
                  .isInstanceOf(MailDeliveryException.class);
              assertThatThrownBy(() -> reset.sendGoogleAccountNotice("google@example.com"))
                  .isInstanceOf(MailDeliveryException.class);
            });
  }

  @Test
  void bothKindsOfMailGoThroughTheSameSender() {
    runner.run(
        context -> {
          // 메일 설정은 하나이고 발송기도 하나다. 어느 타입으로 주입받아도 같은 빈이 온다
          assertThat(context).hasSingleBean(AuthMailSender.class);
          assertThat(context.getBean(PasswordResetMailSender.class))
              .isSameAs(context.getBean(VerificationMailSender.class));
        });
  }

  @Test
  void enabled_usesTheSmtpSenderForPasswordResetToo() {
    runner
        .withPropertyValues(
            "app.mail.enabled=true",
            "spring.mail.username=bot@gmail.com",
            "spring.mail.password=app-password")
        .run(
            context ->
                assertThat(context.getBean(PasswordResetMailSender.class))
                    .isInstanceOf(SmtpVerificationMailSender.class));
  }

  @Test
  void enabled_usesTheSmtpSender() {
    runner
        .withPropertyValues(
            "app.mail.enabled=true",
            "spring.mail.username=bot@gmail.com",
            "spring.mail.password=app-password")
        .run(
            context ->
                assertThat(context.getBean(VerificationMailSender.class))
                    .isInstanceOf(SmtpVerificationMailSender.class));
  }

  @Test
  void enabledWithoutSmtpAccount_failsAtStartup() {
    runner
        .withPropertyValues("app.mail.enabled=true")
        .run(
            context ->
                assertThat(context).hasFailed().getFailure().hasMessageContaining("MAIL_USERNAME"));
  }

  @Test
  void enabledWithOnlyAUsername_failsAtStartup() {
    runner
        .withPropertyValues("app.mail.enabled=true", "spring.mail.username=bot@gmail.com")
        .run(context -> assertThat(context).hasFailed());
  }
}
