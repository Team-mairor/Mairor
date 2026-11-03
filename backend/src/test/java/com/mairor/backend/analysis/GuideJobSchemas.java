package com.mairor.backend.analysis;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * AI 서버와 같은 공유 스키마({@code shared/guide-job})로 가이드 생성 요청·콜백을 검사한다. 테스트는 {@code backend/}에서 돌므로 레포의
 * 파일을 바로 읽는다.
 */
public final class GuideJobSchemas {

  private static final JsonSchema REQUEST =
      load(Path.of("../shared/guide-job/guide_job_request.v2.schema.json"));
  private static final JsonSchema CALLBACK =
      load(Path.of("../shared/guide-job/guide_job_callback.v1.schema.json"));
  // 검사기는 Jackson 2 를 쓴다(앱은 Jackson 3)
  private static final ObjectMapper JSON = new ObjectMapper();

  private GuideJobSchemas() {}

  /**
   * @return 어긋난 곳. 통과하면 빈 문자열
   */
  public static String requestViolations(String json) {
    return violations(REQUEST, json);
  }

  /**
   * @return 어긋난 곳. 통과하면 빈 문자열
   */
  public static String callbackViolations(String json) {
    return violations(CALLBACK, json);
  }

  private static String violations(JsonSchema schema, String json) {
    try {
      Set<ValidationMessage> errors = schema.validate(JSON.readTree(json));
      return errors.stream().map(ValidationMessage::getMessage).collect(Collectors.joining("\n"));
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  private static JsonSchema load(Path file) {
    try {
      return JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012)
          .getSchema(Files.readString(file));
    } catch (IOException e) {
      throw new UncheckedIOException(file.toAbsolutePath() + " 을 읽지 못했습니다.", e);
    }
  }
}
