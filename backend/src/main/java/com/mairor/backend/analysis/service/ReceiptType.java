package com.mairor.backend.analysis.service;

/** 작업 접수 결과. API 명세 v2 AnalysisJobReceipt.receiptType 와 같은 값이다. */
public enum ReceiptType {
  /** 승인된 가이드가 있어 새 작업 없이 그 가이드를 돌려줬다. 회원 분석 요청(API-VIDEO-002)에만 있다. */
  REUSED_GUIDE,
  /** 새 작업을 만들었다. */
  NEW_JOB,
  /** 같은 영상의 진행 중 작업이 있어 그 작업을 돌려줬다. */
  JOINED_JOB
}
