package com.mairor.backend.guides.service;

import tools.jackson.databind.JsonNode;

/**
 * 가이드 단계의 화장 종류를 읽는다. 영상 분석이 렌즈 끼기 단계를 베이스 같은 화장 종류로 잘못 분류해도, 렌즈에는 맞는 화장품이 없으므로 {@link #LENS}로 본다.
 * 단계는 그대로 따라 하는 단계({@code GUIDE})로 남지만 대체할 제품 종류가 없어서 제품 매칭에서는 "없음"이 된다.
 */
public final class GuideStepMakeup {

  public static final String LENS = "lens";

  private static final String LENS_WORD = "렌즈";

  private GuideStepMakeup() {}

  /** 단계 JSON 의 화장 종류. 단계명이나 제품명에 "렌즈"가 있으면 {@link #LENS}. 값이 없으면 빈 문자열. */
  public static String of(JsonNode step) {
    if (contains(step.path("partLabel"), LENS_WORD)
        || contains(step.path("product").path("name"), LENS_WORD)) {
      return LENS;
    }
    return step.path("makeup").asString("");
  }

  private static boolean contains(JsonNode value, String word) {
    return value.isString() && value.asString().contains(word);
  }
}
