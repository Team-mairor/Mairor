package com.mairor.backend.products.collect;

/** 직접 입력 등록 뒤 수집 요청 접수 결과. 로그와 테스트에만 쓰고 회원에게 보이지 않는다. */
public enum IntakeOutcome {
  /** 자동 수집이 꺼져 있다. */
  DISABLED,
  /** 항목이 없거나 직접 입력 항목이 아니다(그 사이 지워지거나 바뀜). */
  NOT_MANUAL,
  /** 자동 수집 소분류가 아니다. */
  TYPE_NOT_COLLECTED,
  /** 회원의 최근 24시간 요청이 한도에 닿았다. */
  DAILY_LIMIT,
  /** 같은 제품이 최근에 찾은 제품 없음·부족 정보 미해결로 끝났다. */
  RECENTLY_TRIED,
  /** 카탈로그에 이미 제품(과 적은 호수)이 있어 수집하지 않고 해결로 끝냈다. */
  RESOLVED_IN_CATALOG,
  /** 카탈로그만으로 풀 수 없다고 정해졌다(후보 여럿, 출처 없는 제품에 호수 없음). */
  UNRESOLVED_IN_CATALOG,
  /** 새 요청을 큐 대기로 넣었다. */
  QUEUED,
  /** 같은 제품의 진행 중 요청에 회원을 붙였다. */
  JOINED
}
