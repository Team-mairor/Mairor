package com.mairor.backend.products.imports;

/**
 * 수집 상품 한 건을 읽다가 찾은 문제. 문제가 하나라도 있으면 그 건은 {@code INVALID}로 기록하고 나머지 건은 계속 처리한다.
 *
 * @param path 문제가 있는 위치. 예: {@code sourceProductId}, {@code shades[0].colors[1].hex}
 * @param code 문제 종류
 * @param message 사람이 읽는 설명 (값 자체는 싣지 않는다)
 */
public record ImportIssue(String path, Code code, String message) {

  /** 이 코드는 적재 기록의 사유로 그대로 나간다. 이름을 바꾸면 기록과 맞지 않는다. */
  public enum Code {
    /** 필수 값이 없거나 비어 있다. */
    REQUIRED,
    /** 값의 JSON 형식(문자열·정수·배열 등)이 계약과 다르다. */
    WRONG_TYPE,
    /** 길이나 개수가 상한을 넘는다. 자르지 않고 거절한다. */
    TOO_LONG,
    /** 값의 모양이 틀리다. 예: HEX 가 {@code #RRGGBB} 대문자가 아니다. */
    INVALID_FORMAT,
    /** 허용 목록에 없는 값이다. */
    INVALID_VALUE,
    /** 모르는 계약 판이다. */
    UNSUPPORTED_CONTRACT_VERSION,
    /** 같이 있어야 하는 값끼리 맞지 않는다. 예: 이름이 있는데 이름 근거가 {@code NONE}. */
    INCONSISTENT,
    /** 같은 건 안에서 겹쳐서는 안 되는 값이 겹친다. */
    DUPLICATE
  }

  @Override
  public String toString() {
    return path + " " + code + ": " + message;
  }
}
