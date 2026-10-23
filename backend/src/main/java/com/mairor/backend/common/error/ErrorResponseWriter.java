package com.mairor.backend.common.error;

import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * 컨트롤러 밖(시큐리티 필터)에서 {@link ErrorResponse}를 직접 응답에 쓴다. 401·403이 {@link GlobalExceptionHandler}와 같은
 * 형식으로 나가게 하는 용도.
 */
@Component
public class ErrorResponseWriter {

  private final ObjectMapper objectMapper;

  public ErrorResponseWriter(ObjectMapper objectMapper) {
    this.objectMapper = objectMapper;
  }

  public void write(HttpServletResponse response, ErrorCode code) throws IOException {
    response.setStatus(code.status().value());
    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
    response.setCharacterEncoding(StandardCharsets.UTF_8.name());
    objectMapper.writeValue(response.getOutputStream(), ErrorResponse.of(code));
  }
}
