package com.mairor.backend.products.collect;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import tools.jackson.databind.ObjectMapper;

/** {@code catalog.collect.queue-url}이 있으면 SQS 큐, 없으면 보내지 않는 큐를 만든다. SQS 클라이언트는 있을 때만 만든다. */
@Configuration(proxyBeanMethods = false)
class CollectJobQueueConfig {

  @Bean
  CollectJobQueue collectJobQueue(CatalogCollectProperties properties, ObjectMapper json) {
    if (!properties.queueEnabled()) {
      return new CollectJobQueue() {
        @Override
        public boolean enabled() {
          return false;
        }

        @Override
        public void send(CollectJobMessage message) {
          throw new IllegalStateException("수집 큐가 설정되지 않았다");
        }
      };
    }
    SqsClient client = SqsClient.builder().region(Region.of(properties.queueRegion())).build();
    return new SqsCollectJobQueue(client, properties.queueUrl(), json);
  }
}
