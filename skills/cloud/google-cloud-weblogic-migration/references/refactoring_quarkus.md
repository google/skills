# WebLogic to Quarkus Refactoring Guide

This guide provides patterns for refactoring WebLogic and Java EE (Jakarta EE)
components to Quarkus. Quarkus uses Jakarta EE standards (like CDI, JTA, JAX-RS)
which makes the transition from WebLogic relatively straightforward, but
requires replacing specific WebLogic features and EJB specific details.

## Table of Contents

*   [1. EJB to Quarkus Beans (CDI)](#1-ejb-to-quarkus-beans-cdi) (Line 17)
*   [2. Dependency Injection (JNDI to CDI Inject)](#2-dependency-injection-jndi-to-cdi-inject) (Line 60)
*   [3. Transaction Management](#3-transaction-management) (Line 112)
*   [4. Logging](#4-logging) (Line 143)

--------------------------------------------------------------------------------

## 1. EJB to Quarkus Beans (CDI)

Quarkus does not support full EJB container features (like remote EJBs, EJB
timers). EJB Session Beans should be converted to standard CDI beans.

### Stateless Session Beans (SLSB)

Convert to `@ApplicationScoped` (singleton-like) or `@RequestScoped` beans.

**Legacy EJB:**

```java
import javax.ejb.Stateless;

@Stateless
public class OrderServiceBean implements OrderService {
    public void placeOrder(Order order) { ... }
}
```

**Quarkus (CDI):**

```java
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class OrderServiceBean implements OrderService {
    @Override
    public void placeOrder(Order order) { ... }
}
```

### Stateful Session Beans (SFSB)

> [!WARNING] Serverless environments (like Cloud Run) are designed to be
> stateless. Stateful Session Beans should be refactored to be stateless,
> storing session state in an external cache (e.g., Memorystore/Redis) or
> database.

If you must keep state, you can use `@SessionScoped` (if using Quarkus RESTEasy
with session support), but this is discouraged for cloud-native serverless
deployments.

## 2. Dependency Injection (JNDI to CDI Inject)

Replace `@EJB` and JNDI lookups with `@Inject`.

**Legacy EJB Injection:**

```java
@EJB
private OrderService orderService;
```

**Quarkus (CDI):**

```java
import jakarta.inject.Inject;

public class OrderResource {
    @Inject
    OrderService orderService;
}
```

For configuration properties (MicroProfile Config): Replace JNDI env-entry with
`@ConfigProperty`.

**Legacy JNDI Env Entry:**

```java
InitialContext ctx = new InitialContext();
String myConfig = (String) ctx.lookup("java:comp/env/myConfigParam");
```

**Quarkus:**

```java
import org.eclipse.microprofile.config.inject.ConfigProperty;
import jakarta.inject.Inject;

@ApplicationScoped
public class MyService {
    @Inject
    @ConfigProperty(name = "my.config.param")
    String myConfig;
}
```

Define in `src/main/resources/application.properties`:

```properties
my.config.param=some-value
```

## 3. Transaction Management

Quarkus supports JTA `@Transactional` (from `jakarta.transaction`), which is
very similar to EJB CMT.

**Legacy EJB CMT:**

```java
import javax.ejb.TransactionAttribute;
import javax.ejb.TransactionAttributeType;

@Stateless
public class OrderServiceBean {
    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void placeOrder(Order order) { ... }
}
```

**Quarkus:**

```java
import jakarta.transaction.Transactional;
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class OrderServiceBean {
    @Transactional(Transactional.TxType.REQUIRED)
    public void placeOrder(Order order) { ... }
}
```

## 4. Logging

Quarkus uses JBoss Logging by default, but also supports SLF4J.

**Quarkus (using SLF4J):**

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@ApplicationScoped
public class MyService {
    private static final Logger log = LoggerFactory.getLogger(MyService.class);

    public void doWork() {
        log.info("Doing work in Quarkus");
    }
}
```
