# WebLogic to Spring Boot Refactoring Guide

This guide provides patterns for refactoring WebLogic and Java EE (Jakarta EE)
components to Spring Boot.

## Table of Contents

*   [1. EJB to Spring Beans](#1-ejb-to-spring-beans) (Line 15)
*   [2. Dependency Injection (JNDI to Spring DI)](#2-dependency-injection-jndi-to-spring-di) (Line 72)
*   [3. Transaction Management](#3-transaction-management) (Line 126)
*   [4. Logging](#4-logging) (Line 157)

--------------------------------------------------------------------------------

## 1. EJB to Spring Beans

### Stateless Session Beans (SLSB)

Stateless EJBs are easily mapped to Spring `@Service` or `@Component` beans.
Spring beans are singletons by default, which is generally appropriate if they
are stateless.

**Legacy EJB:**

```java
import javax.ejb.Stateless;

@Stateless(name = "OrderService")
public class OrderServiceBean implements OrderService {
    public void placeOrder(Order order) {
        // Business logic
    }
}
```

**Spring Boot:**

```java
import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService {
    @Override
    public void placeOrder(Order order) {
        // Business logic
    }
}
```

### Stateful Session Beans (SFSB)

> [!WARNING] Serverless environments (like Cloud Run) are designed to be
> stateless. Stateful Session Beans should be refactored to be stateless,
> storing session state in an external cache (e.g., Memorystore/Redis) or
> database.

If you must keep session state in the application tier (not recommended for
serverless scaled-out instances): Use Spring `@SessionScope`.

```java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class UserSession {
    private User user;
    // getter/setter
}
```

## 2. Dependency Injection (JNDI to Spring DI)

Replace manual JNDI lookups with Spring's `@Autowired` or `@Resource`.

**Legacy JNDI Lookup:**

```java
InitialContext ctx = new InitialContext();
OrderService orderService = (OrderService) ctx.lookup("java:comp/env/ejb/OrderService");
```

**Spring Boot:**

```java
import org.springframework.beans.factory.annotation.Autowired;

@RestController
public class OrderController {

    @Autowired
    private OrderService orderService;

    // ...
}
```

For configuration properties (previously looked up via JNDI environment
entries): Use `@Value` or `@ConfigurationProperties`.

**Legacy JNDI Env Entry:**

```java
InitialContext ctx = new InitialContext();
String myConfig = (String) ctx.lookup("java:comp/env/myConfigParam");
```

**Spring Boot:**

```java
import org.springframework.beans.factory.annotation.Value;

@Component
public class MyComponent {
    @Value("${my.config.param}")
    private String myConfig;
}
```

Define the value in `application.properties`:

```properties
my.config.param=some-value
```

## 3. Transaction Management

Replace EJB Container-Managed Transactions (CMT) with Spring's `@Transactional`.

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

**Spring Boot:**

```java
import org.springframework.transaction.annotation.Transactional;
import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService {
    @Override
    @Transactional
    public void placeOrder(Order order) { ... }
}
```

## 4. Logging

Replace `weblogic.logging` (if used) or standard `java.util.logging` with SLF4J
(backed by Logback in Spring Boot).

**Legacy:**

```java
import java.util.logging.Logger;
// or import weblogic.logging.NonCatalogLogger;

public class MyClass {
    private static final Logger log = Logger.getLogger(MyClass.class.getName());

    public void doWork() {
        log.info("Doing work");
    }
}
```

**Spring Boot:**

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class MyClass {
    private static final Logger log = LoggerFactory.getLogger(MyClass.class);

    public void doWork() {
        log.info("Doing work");
    }
}
```

(Alternatively, use Lombok's `@Slf4j` annotation).
