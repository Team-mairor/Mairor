package com.mairor.backend.products.collect;

import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;
import tools.jackson.databind.ObjectMapper;

/** SQS 로 보낸다. 자격 증명은 AWS 기본 공급자 체인(EC2 역할)이다. 오류 메시지에는 큐 주소만 담는다. */
class SqsCollectJobQueue implements CollectJobQueue {

  private final SqsClient client;
  private final String queueUrl;
  private final ObjectMapper json;

  SqsCollectJobQueue(SqsClient client, String queueUrl, ObjectMapper json) {
    this.client = client;
    this.queueUrl = queueUrl;
    this.json = json;
  }

  @Override
  public boolean enabled() {
    return true;
  }

  @Override
  public void send(CollectJobMessage message) {
    String body = json.writeValueAsString(message);
    try {
      client.sendMessage(SendMessageRequest.builder().queueUrl(queueUrl).messageBody(body).build());
    } catch (SdkException e) {
      throw new CollectQueueException("수집 큐에 보내지 못했다: " + queueUrl, e);
    }
  }
}
