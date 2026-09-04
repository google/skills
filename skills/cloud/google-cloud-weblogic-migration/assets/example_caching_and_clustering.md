# Stateful Session Beans (SFSB), Coherence Caching, & Session Replication Modernization Guide

Legacy WebLogic applications rely on **In-Memory HTTP Session Replication**
across WebLogic Managed Server cluster members, **Oracle Coherence** data grids,
or EJB 2.x/3.x **Stateful Session Beans (SFSBs)** (`@Stateful`,
`ejbPassivate()`, `ejbActivate()`) to maintain conversational client state
across requests.

In cloud-native serverless container environments (Google Cloud Run / Google
Kubernetes Engine / Google Cloud Functions), container replicas are ephemeral
and stateless. All in-memory conversational state and clustering protocols must
be externalized to managed cloud data grids.

--------------------------------------------------------------------------------

## 1. Stateful Session Beans (SFSB) to Stateless Services & Redis

In WebLogic, `@Stateful` session beans hold conversational state for a specific
client across multiple method invocations.

### Before: Legacy WebLogic Stateful Session Bean (`@Stateful`)

```java
import javax.ejb.Stateful;
import javax.ejb.Remove;

@Stateful
public class PatientCartBean implements PatientCart {
    private List<Long> selectedPrescriptionIds = new ArrayList<>();

    public void addPrescription(Long prescriptionId) {
        selectedPrescriptionIds.add(prescriptionId);
    }

    @Remove
    public List<Long> checkout() {
        return selectedPrescriptionIds;
    }
}
```

### After: Stateless Spring / CDI Service with Google Cloud Memorystore (Redis)

Refactor `@Stateful` EJBs into **stateless Spring Services (`@Service`)** or
Quarkus `@ApplicationScoped` beans by externalizing conversational state into
**Google Cloud Memorystore for Redis**:

#### Spring Boot with Spring Data Redis

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import java.time.Duration;
import java.util.List;

@Service
public class PatientCartService {
    @Autowired
    private RedisTemplate<String, Object> redisTemplate;

    private String getCartKey(String patientId) {
        return "cart:patient:" + patientId;
    }

    public void addPrescription(String patientId, Long prescriptionId) {
        String key = getCartKey(patientId);
        redisTemplate.opsForList().rightPush(key, prescriptionId);
        redisTemplate.expire(key, Duration.ofHours(2)); // TTL for conversational state
    }

    public List<Object> checkout(String patientId) {
        String key = getCartKey(patientId);
        List<Object> items = redisTemplate.opsForList().range(key, 0, -1);
        redisTemplate.delete(key); // Clear state upon checkout
        return items;
    }
}
```

--------------------------------------------------------------------------------

## 2. WebLogic HTTP Session Replication & Oracle Coherence to Redis

Legacy WebLogic web modules configure `<session-descriptor>` in `weblogic.xml`
for in-memory session replication or Coherence Web clustering.

### Before: Legacy `weblogic.xml` Session Clustering

```xml
<session-descriptor>
    <persistent-store-type>replicated_if_clustered</persistent-store-type>
    <sharing-enabled>true</sharing-enabled>
</session-descriptor>
```

### After: Spring Session Data Redis (Spring Boot)

In Spring Boot, replace WebLogic in-memory replication with **Spring Session
Data Redis**, which transparently backs `HttpSession` with Google Cloud
Memorystore for Redis without requiring code changes in controllers:

```xml
<!-- pom.xml -->
<dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

```properties
# application.properties
spring.session.store-type=redis
spring.data.redis.host=${REDIS_HOST:10.0.0.3}
spring.data.redis.port=6379
spring.session.redis.namespace=medimed:session
```

### After: Quarkus Redis Cache & Session

In Quarkus, back HTTP sessions or application caches using the
`quarkus-redis-client` and `quarkus-cache` extensions:

```xml
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-redis-client</artifactId>
</dependency>
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-cache</artifactId>
</dependency>
```

```properties
# application.properties
quarkus.redis.hosts=redis://${REDIS_HOST:10.0.0.3}:6379
quarkus.cache.type=redis
```

```java
import io.quarkus.cache.CacheResult;
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class MedicalCatalogService {

    // Transparently caches result in Google Cloud Memorystore for Redis
    @CacheResult(cacheName = "drug-catalog")
    public DrugDetails getDrugDetails(String drugCode) {
        // Heavy database lookup...
    }
}
```
