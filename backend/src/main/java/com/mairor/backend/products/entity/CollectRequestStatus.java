package com.mairor.backend.products.entity;

/**
 * 화장품 수집 요청의 상태. {@link #QUEUED}·{@link #SENT}는 진행 중이고 나머지는 끝난 상태다.
 *
 * <ul>
 *   <li>{@link #QUEUED}: 저장했고 아직 큐에 보내지 못했다
 *   <li>{@link #SENT}: 큐에 보냈고 수집 워커의 결과를 기다린다
 *   <li>{@link #RESOLVED}: 요청한 부족 정보가 카탈로그에 생겼다
 *   <li>{@link #UNRESOLVED}: 수집·적재는 끝났지만 부족 정보가 풀리지 않았다(후보 여럿, 호수 없음 등)
 *   <li>{@link #NOT_FOUND}: 일치 제품이 없거나 수집할 공식 홈이 없다
 *   <li>{@link #FAILED}: 차단·통신·적재 오류, 또는 결과가 오지 않았다
 * </ul>
 */
public enum CollectRequestStatus {
  QUEUED,
  SENT,
  RESOLVED,
  UNRESOLVED,
  NOT_FOUND,
  FAILED;

  public boolean isOpen() {
    return this == QUEUED || this == SENT;
  }
}
