# Servlet Filters, Listeners, & Web Descriptors (`web.xml` / `weblogic.xml`) Modernization Guide

Legacy WebLogic web modules heavily use complex `web.xml` filter chains
(`javax.servlet.Filter`), `weblogic.xml` security role assignments, and
lifecycle listeners (`ServletContextListener`, `HttpSessionListener`,
`ServletRequestListener`).

When refactoring to Spring Boot or Quarkus microservices, these imperative
servlet artifacts must be modernized into declarative web filters, request
interceptors, or Spring Security filters.

--------------------------------------------------------------------------------

## 1. Servlet Filters (`javax.servlet.Filter`) to Spring / Quarkus Filters

In WebLogic, filters are declared in `web.xml` via `<filter>` and
`<filter-mapping>` tags to intercept incoming HTTP requests for logging, header
manipulation, or custom authentication.

### Before: Legacy `web.xml` Filter Declaration

```xml
<filter>
    <filter-name>AuditLogFilter</filter-name>
    <filter-class>com.acme.medimed.filter.AuditLogFilter</filter-class>
</filter>
<filter-mapping>
    <filter-name>AuditLogFilter</filter-name>
    <url-pattern>/api/*</url-pattern>
</filter-mapping>
```

```java
import javax.servlet.*;
import javax.servlet.http.HttpServletRequest;
import java.io.IOException;

public class AuditLogFilter implements Filter {
    public void doFilter(ServletRequest req, ServletResponse resp, FilterChain chain) throws IOException, ServletException {
        HttpServletRequest httpReq = (HttpServletRequest) req;
        System.out.println("Intercepted request to: " + httpReq.getRequestURI());
        chain.doFilter(req, resp);
    }
}
```

### After: Spring Boot `@WebFilter` / `OncePerRequestFilter`

In Spring Boot, replace `web.xml` declarations with `@WebFilter` (accompanied by
`@ServletComponentScan` on the main application class) or implement Spring
Security's `OncePerRequestFilter`:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

@Component
public class AuditLogFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {

        if (request.getRequestURI().startsWith("/api/")) {
            logger.info("Intercepted request to: " + request.getRequestURI());
        }
        filterChain.doFilter(request, response);
    }
}
```

### After: Quarkus JAX-RS `@Provider` / `ContainerRequestFilter`

In Quarkus, implement a JAX-RS `ContainerRequestFilter` annotated with
`@Provider`:

```java
import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerRequestFilter;
import jakarta.ws.rs.ext.Provider;
import org.jboss.logging.Logger;
import java.io.IOException;

@Provider
public class AuditLogFilter implements ContainerRequestFilter {
    private static final Logger LOG = Logger.getLogger(AuditLogFilter.class);

    @Override
    public void filter(ContainerRequestContext requestContext) throws IOException {
        if (requestContext.getUriInfo().getPath().startsWith("/api/")) {
            LOG.infof("Intercepted request to: %s", requestContext.getUriInfo().getPath());
        }
    }
}
```

--------------------------------------------------------------------------------

## 2. Lifecycle Listeners (`ServletContextListener` / `HttpSessionListener`)

Legacy applications use `ServletContextListener.contextInitialized()` to execute
startup logic (such as loading reference data or initializing custom connection
pools) and `HttpSessionListener` to track active user sessions.

### After: Spring Boot Startup Interceptors (`ApplicationRunner` / `@EventListener`)

Replace `ServletContextListener` with Spring Boot's `ApplicationRunner` or
`@EventListener(ApplicationReadyEvent.class)`:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ReferenceDataStartupLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) throws Exception {
        // Execute startup initialization logic previously in ServletContextListener.contextInitialized()
        System.out.println("Loading reference medical catalogs into cache on startup...");
    }
}
```

### After: Quarkus Startup Event (`@Observes StartupEvent`)

In Quarkus, observe the `StartupEvent` using CDI:

```java
import io.quarkus.runtime.StartupEvent;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;

@ApplicationScoped
public class ReferenceDataStartupLoader {

    void onStart(@Observes StartupEvent ev) {
        // Execute startup initialization logic
        System.out.println("Loading reference medical catalogs into cache on startup...");
    }
}
```

--------------------------------------------------------------------------------

## 3. `weblogic.xml` Security Role Assignments to Declarative Security

In WebLogic, `weblogic.xml` maps security role names declared in `web.xml`
(`<security-role>`) to WebLogic realm users and groups
(`<security-role-assignment>`).

### After: Stripping `weblogic.xml` & Enforcing Role Claims in Cloud IAM

When migrating to Spring Security or Quarkus Security:

1.  **Delete `weblogic.xml` and `web.xml`**: Imperative XML descriptor role
    mappings are obsolete.
2.  **Map Roles in Identity Provider (IdP)**: Configure user-to-group mappings
    in your cloud identity provider (Google Cloud Identity, Okta, or Keycloak).
3.  **Enforce via Annotations**: Let Spring Security
    (`@PreAuthorize("hasRole('ADMIN')")`) or Quarkus (`@RolesAllowed("ADMIN")`)
    evaluate the role claims directly from incoming JWT bearer tokens.
