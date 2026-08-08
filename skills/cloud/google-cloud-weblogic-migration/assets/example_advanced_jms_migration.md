# Advanced WebLogic JMS & Messaging Modernization Guide

This guide provides concrete transformation recipes for modernizing advanced
WebLogic JMS features (Unit-of-Order, Message Selectors, Poison Messages/Dead
Letter Queues, and Messaging Bridges) when migrating to Google Cloud Pub/Sub in
Spring Boot and Quarkus microservices.

--------------------------------------------------------------------------------

## 1. JMS Unit-of-Order (UOO) to GCP Pub/Sub Ordering Keys

In legacy WebLogic JMS, setting a `UnitOfOrder` message property guarantees that
all messages sharing the same order name are delivered sequentially by a single
consumer instance.

### Before: Legacy WebLogic JMS Unit-of-Order

```java
// Legacy WebLogic JMS Unit-of-Order
import weblogic.jms.extensions.WLMessageProducer;
import javax.jms.*;

public class OrderDispatcher {
    public void sendOrderedTransaction(Session session, MessageProducer producer, String accountId, String payload) throws JMSException {
        TextMessage msg = session.createTextMessage(payload);
        // Set WebLogic specific Unit-of-Order property
        msg.setStringProperty("JMS_BEA_UnitOfOrder", accountId);
        producer.send(msg);
    }
}
```

### After: Google Cloud Pub/Sub Ordering Keys

In Google Cloud Pub/Sub, message ordering is guaranteed within a topic by
setting an **Ordering Key** on published messages and enabling message ordering
on the subscription.

#### Spring Boot (Spring Cloud GCP Pub/Sub)

```java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class OrderDispatcher {
    @Autowired
    private PubSubTemplate pubSubTemplate;

    public void sendOrderedTransaction(String accountId, String payload) {
        // Publish message with Ordering Key set to accountId
        pubSubTemplate.publish("account-transactions-topic", payload, Collections.emptyMap(), accountId);
    }
}
```

#### Pub/Sub Subscription Configuration (Terraform / gcloud)

```hcl
resource "google_pubsub_subscription" "ordered_sub" {
  name                   = "account-transactions-sub"
  topic                  = google_pubsub_topic.transactions.name
  enable_message_ordering = true # CRITICAL: Required for ordering keys
}
```

--------------------------------------------------------------------------------

## 2. JMS Message Selectors to Pub/Sub Subscription Filters

WebLogic JMS consumers frequently use SQL-92 message selectors (e.g.,
`priority = 'HIGH' AND region = 'US'`) to filter incoming messages at the broker
level.

### Before: Legacy WebLogic JMS Message Selector

```java
// Legacy WebLogic JMS Selector
String selector = "hospital_code = 'GENERAL' AND emergency_level >= 3";
MessageConsumer consumer = session.createConsumer(queue, selector);
```

### After: Google Cloud Pub/Sub Filter Expressions

GCP Pub/Sub supports broker-level **Subscription Filter Expressions** matching
message attributes.

#### Spring Boot Publisher (Setting Attributes)

```java
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.messaging.support.MessageBuilder;

public void publishAlert(String hospitalCode, int emergencyLevel, String payload) {
    Map<String, String> attributes = Map.of(
        "hospital_code", hospitalCode,
        "emergency_level", String.valueOf(emergencyLevel)
    );
    pubSubTemplate.publish("emergency-alerts-topic", payload, attributes);
}
```

#### Pub/Sub Subscription Filter Configuration

```hcl
resource "google_pubsub_subscription" "filtered_sub" {
  name   = "general-hospital-emergencies-sub"
  topic  = google_pubsub_topic.alerts.name

  # Pub/Sub filter syntax matching SQL-92 selector logic
  filter = "attributes.hospital_code = \"GENERAL\" AND attributes.emergency_level >= \"3\""
}
```

--------------------------------------------------------------------------------

## 3. Poison Messages & Dead Letter Queues (DLQ)

In WebLogic JMS, error destinations and redelivery limits prevent failing
messages (poison messages) from looping infinitely.

### After: Google Cloud Pub/Sub Dead-Letter Topics & Exponential Backoff

Configure Dead-Letter Topics (DLT) and retry policies directly on the GCP
Pub/Sub subscription:

```hcl
resource "google_pubsub_topic" "dead_letter_topic" {
  name = "emergency-alerts-dlq"
}

resource "google_pubsub_subscription" "robust_sub" {
  name  = "emergency-alerts-sub"
  topic = google_pubsub_topic.alerts.name

  # Dead-Letter Policy (Poison Message Handling)
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter_topic.id
    max_delivery_attempts = 5
  }

  # Exponential Backoff Retry Policy
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  # Acknowledge deadline for long-running message consumers (up to 600s)
  ack_deadline_seconds = 600
}
```

> [!WARNING] **Ack Deadlines & Consumer Idempotency**: If message processing
> exceeds `ack_deadline_seconds`, GCP Pub/Sub will automatically redeliver the
> message to another worker instance. All consumer logic MUST be designed to be
> completely **idempotent** (e.g., checking message deduplication IDs in Cloud
> SQL/Redis before execution) to prevent duplicate processing.

--------------------------------------------------------------------------------

## 4. WebLogic Messaging Bridges to GCP Pub/Sub Connectors

WebLogic Messaging Bridges connect external message brokers (e.g., IBM MQ, Tibco
EMS, or Apache ActiveMQ) to internal WebLogic JMS queues.

### After: Cloud-Native Bridge Strategies

In serverless containers, replace embedded WebLogic Messaging Bridges with:

1.  **Google Cloud Pub/Sub Connectors**: Use managed connectors (like
    Kafka-to-PubSub or MQ-to-PubSub sinks/sources in Google Cloud Dataflow).
2.  **Dedicated Ingestion Worker Microservice**: If specific MQ protocols are
    required, deploy a lightweight Spring Boot worker using Spring JMS
    (`spring-boot-starter-activemq` or IBM MQ client) that listens to the
    external broker and forwards messages asynchronously into GCP Pub/Sub
    topics.
