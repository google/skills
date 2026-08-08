# Example: JMS Message-Driven Bean to GCP Pub/Sub

This example shows how to migrate a WebLogic Message-Driven Bean (MDB) listening
to a JMS Queue to a GCP Pub/Sub subscriber in both Spring Boot and Quarkus.

## 1. Legacy WebLogic JMS MDB (Before)

An EJB MDB that listens to `jms/OrderQueue` and processes incoming text
messages.

```java
package com.example.legacy;

import javax.ejb.MessageDriven;
import javax.ejb.ActivationConfigProperty;
import javax.jms.Message;
import javax.jms.MessageListener;
import javax.jms.TextMessage;

@MessageDriven(
    name = "OrderProcessorMDB",
    activationConfig = {
        @ActivationConfigProperty(propertyName = "destinationType", propertyValue = "javax.jms.Queue"),
        @ActivationConfigProperty(propertyName = "destination", propertyValue = "jms/OrderQueue")
    }
)
public class OrderProcessorMDB implements MessageListener {

    @Override
    public void onMessage(Message message) {
        try {
            if (message instanceof TextMessage) {
                String payload = ((TextMessage) message).getText();
                System.out.println("Processing order: " + payload);
                // Business logic to process order
            } else {
                System.err.println("Message of wrong type: " + message.getClass().getName());
            }
        } catch (Exception e) {
            System.err.println("Error processing message: " + e.getMessage());
            // In EJB, rollback might be triggered here depending on configuration
        }
    }
}
```

--------------------------------------------------------------------------------

## 2. Spring Boot Migration with Spring Cloud GCP Pub/Sub (After)

In Spring Boot, we use `PubSubTemplate` to subscribe to a Pub/Sub subscription
named `order-subscription` (which is subscribed to the `order-topic`).

### Maven Dependency

Ensure you have the Spring Cloud GCP Pub/Sub starter:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
```

### Subscriber Code

```java
package com.example.modern;

import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProcessorSubscriber {

    @Autowired
    private PubSubTemplate pubSubTemplate;

    // Start listening when the application is ready
    @EventListener(ApplicationReadyEvent.class)
    public void subscribeToOrders() {
        String subscriptionName = "order-subscription";

        pubSubTemplate.subscribe(subscriptionName, (BasicAcknowledgeablePubsubMessage message) -> {
            String payload = message.getPubsubMessage().getData().toStringUtf8();
            try {
                System.out.println("Processing order from Pub/Sub: " + payload);
                // Business logic to process order

                // Acknowledge the message upon successful processing
                message.ack();
            } catch (Exception e) {
                System.err.println("Failed to process order: " + e.getMessage());
                // Nack (negative acknowledge) to redeliver the message
                message.nack();
            }
        });
    }
}
```

--------------------------------------------------------------------------------

## 3. Quarkus Migration with Google Cloud Pub/Sub Client (After)

In Quarkus, we use the standard GCP Pub/Sub Java SDK client, initialized on
application startup.

### Maven Dependency

```xml
<dependency>
    <groupId>io.quarkiverse.googlecloudservices</groupId>
    <artifactId>quarkus-google-cloud-pubsub</artifactId>
</dependency>
```

### Subscriber Code

```java
package com.example.modern;

import com.google.cloud.pubsub.v1.AckReplyConsumer;
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import io.quarkus.runtime.ShutdownEvent;
import io.quarkus.runtime.StartupEvent;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;
import org.eclipse.microprofile.config.inject.ConfigProperty;

@ApplicationScoped
public class OrderProcessorSubscriber {

    @ConfigProperty(name = "gcp.project.id")
    String projectId;

    @ConfigProperty(name = "gcp.pubsub.order-subscription")
    String subscriptionId;

    private Subscriber subscriber;

    void onStart(@Observes StartupEvent ev) {
        ProjectSubscriptionName subscriptionName = ProjectSubscriptionName.of(projectId, subscriptionId);

        MessageReceiver receiver = (PubsubMessage message, AckReplyConsumer consumer) -> {
            String payload = message.getData().toStringUtf8();
            try {
                System.out.println("Processing order from Quarkus Pub/Sub: " + payload);
                // Business logic to process order
                consumer.ack();
            } catch (Exception e) {
                System.err.println("Failed to process order: " + e.getMessage());
                consumer.nack();
            }
        };

        subscriber = Subscriber.newBuilder(subscriptionName, receiver).build();
        // Start the subscriber asynchronously
        subscriber.startAsync().awaitRunning();
    }

    void onStop(@Observes ShutdownEvent ev) {
        if (subscriber != null) {
            // Stop the subscriber when application stops
            subscriber.stopAsync().awaitTerminated();
        }
    }
}
```

### Configuration (`application.properties`)

```properties
gcp.project.id=my-gcp-project
gcp.pubsub.order-subscription=order-subscription
```
