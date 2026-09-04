# Example: Security Migration (JAAS to Spring Security OIDC)

This example shows how to migrate from legacy WebLogic-managed security (often
based on JAAS and web.xml constraints) to a modern OAuth2/OIDC resource server
using Spring Security.

## 1. Legacy WebLogic Security (Before)

Typically configured in `web.xml` and `weblogic.xml`, defining security
constraints and mapping roles to WebLogic users/groups.

### `web.xml` (Security Constraints)

```xml
<security-constraint>
    <web-resource-collection>
        <web-resource-name>AdminResources</web-resource-name>
        <url-pattern>/admin/*</url-pattern>
    </web-resource-collection>
    <auth-constraint>
        <role-name>AdminRole</role-name>
    </auth-constraint>
</security-constraint>

<login-config>
    <auth-method>BASIC</auth-method>
    <realm-name>myrealm</realm-name>
</login-config>

<security-role>
    <role-name>AdminRole</role-name>
</security-role>
```

### `weblogic.xml` (Role Mapping)

Maps the logical role `AdminRole` to a physical WebLogic group `Administrators`.

```xml
<weblogic-web-app>
    <security-role-assignment>
        <role-name>AdminRole</role-name>
        <principal-name>Administrators</principal-name>
    </security-role-assignment>
</weblogic-web-app>
```

### Java Code (Checking Roles Programmatically)

```java
public void doAdminTask(HttpServletRequest request) {
    if (request.isUserInRole("AdminRole")) {
        // Perform admin task
    } else {
        throw new SecurityException("Unauthorized");
    }
}
```

--------------------------------------------------------------------------------

## 2. Spring Boot Migration with OAuth2/OIDC (After)

In Spring Boot, we secure endpoints using Spring Security. We configure the
application as an OAuth2 Resource Server, validating JWTs issued by an Identity
Provider (e.g., Google Identity Platform).

### Maven Dependencies

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

### Security Configuration

```java
package com.example.modern;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                // Replace web.xml constraints
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(new MyRoleConverter()))
            );
        return http.build();
    }
}
```

### Role Converter

Convert JWT claims (e.g., groups or roles from the token) to Spring Security
GrantedAuthorities.

```java
package com.example.modern;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;

public class MyRoleConverter implements Converter<Jwt, AbstractAuthenticationToken> {
    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        // Extract roles/groups from JWT claim (e.g., "roles" or "groups")
        List<String> roles = jwt.getClaimAsStringList("roles");

        Collection<GrantedAuthority> authorities = roles.stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role.toUpperCase()))
                .collect(Collectors.toList());

        return new JwtAuthenticationToken(jwt, authorities);
    }
}
```

### Java Code (Method Security)

Instead of `request.isUserInRole`, use Spring Security's `@PreAuthorize` or
standard `SecurityContextHolder`.

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AdminService {

    @PreAuthorize("hasRole('ROLE_ADMIN')")
    public void doAdminTask() {
        // Perform admin task
    }
}
```

### Configuration (`application.properties`)

Point to the Identity Provider's JWK Set URI to validate tokens.

```properties
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://www.googleapis.com/oauth2/v3/certs
```

*(Example configuration for Google OAuth2. Change to your IdP endpoint).*

--------------------------------------------------------------------------------

## 3. Quarkus Migration with OIDC (After)

Quarkus provides first-class support for OpenID Connect (OIDC) and JWT bearer
token authentication.

### Maven Dependencies

```xml
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-oidc</artifactId>
</dependency>
```

### Java Code (Method Security & Role Checks)

Use standard Jakarta Security annotations (`@RolesAllowed`) directly on REST
endpoints or service methods:

```java
package com.example.modern;

import jakarta.annotation.security.RolesAllowed;
import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.Response;
import io.quarkus.security.identity.SecurityIdentity;

@Path("/admin")
public class AdminResource {

    @Inject
    SecurityIdentity securityIdentity;

    @GET
    @Path("/dashboard")
    @RolesAllowed("ADMIN") // Replaces legacy web.xml auth-constraint
    public Response getDashboard() {
        // Access user principal and attributes cleanly
        String username = securityIdentity.getPrincipal().getName();
        return Response.ok("Welcome Admin: " + username).build();
    }
}
```

### Configuration (`application.properties`)

Configure Quarkus to validate JWT bearer tokens against your OIDC provider or
Google Cloud Identity:

```properties
# Configure Quarkus OIDC application type as bearer token service
quarkus.oidc.application-type=service
quarkus.oidc.auth-server-url=https://accounts.google.com
quarkus.oidc.client-id=my-gcp-client-id
```
