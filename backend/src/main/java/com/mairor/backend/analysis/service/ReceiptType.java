package com.mairor.backend.analysis.service;

/**
 * 작업 접수 결과. API 명세 v2 AnalysisJobReceipt.receiptType 와 같은 값이다. 승인 가이드 재사용({@code REUSED_GUIDE})은
 * 사용자 API(6단계)에서 더한다.
 */
public enum ReceiptType {
  /** 새 작업을 만들었다. */
  NEW_JOB,
  /** 같은 영상의 진행 중 작업이 있어 그 작업을 돌려줬다. */
  JOINED_JOB
}
