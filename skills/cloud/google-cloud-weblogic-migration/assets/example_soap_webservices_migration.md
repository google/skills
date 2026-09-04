# WebLogic SOAP Web Services (JAX-WS / JAX-RPC) Modernization Guide

Legacy WebLogic monoliths (especially WebLogic 10.3 / 11g / 12c) frequently
expose and consume SOAP Web Services using JAX-WS (`@WebService`, `@WebMethod`),
JAX-RPC, `weblogic.wsee.*`, and WS-Security. This guide provides recipes for
hosting legacy SOAP endpoints in Spring Boot and Quarkus, decoupling internal
SOAP calls into REST/gRPC, and modernizing WS-Security.

--------------------------------------------------------------------------------

## 1. Hosting Legacy SOAP Endpoints for Backwards Compatibility

When external enterprise clients (e.g., hospital networks, government agencies)
cannot immediately upgrade to REST/JSON, you must continue hosting the legacy
SOAP WSDL contract from your cloud-native microservice.

### Before: Legacy WebLogic JAX-WS Endpoint

```java
import javax.jws.WebService;
import javax.jws.WebMethod;

@WebService(serviceName = "PatientLookupService", targetNamespace = "http://medimed.acme.com/")
public class PatientLookupServiceImpl {
    @WebMethod
    public PatientRecord getPatientBySSN(String ssn) {
        // Fetch patient...
    }
}
```

### After: Spring Boot with Apache CXF / Spring Web Services

In Spring Boot, use **Apache CXF** or **Spring Web Services** to host the SOAP
endpoint without needing a full Java EE application server.

#### Spring Boot Apache CXF (`pom.xml` & Configuration)

```xml
<dependency>
    <groupId>org.apache.cxf</groupId>
    <artifactId>cxf-spring-boot-starter-jaxws</artifactId>
    <version>4.0.3</version>
</dependency>
```

```java
import org.apache.cxf.Bus;
import org.apache.cxf.jaxws.EndpointImpl;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import jakarta.xml.ws.Endpoint;

@Configuration
public class SoapWebServiceConfig {
    @Autowired
    private Bus bus;

    @Autowired
    private PatientLookupServiceImpl patientLookupService;

    @Bean
    public Endpoint endpoint() {
        EndpointImpl endpoint = new EndpointImpl(bus, patientLookupService);
        endpoint.publish("/PatientLookupService"); // Exposes WSDL at /services/PatientLookupService?wsdl
        return endpoint;
    }
}
```

### After: Quarkus with Quarkus CXF

In Quarkus, use the official `quarkus-cxf` extension to host JAX-WS endpoints
with native compilation support:

```xml
<dependency>
    <groupId>io.quarkiverse.cxf</groupId>
    <artifactId>quarkus-cxf</artifactId>
</dependency>
```

```properties
# application.properties
quarkus.cxf.endpoint."/PatientLookupService".implementor=com.acme.medimed.soap.PatientLookupServiceImpl
```

--------------------------------------------------------------------------------

## 2. Decoupling Internal SOAP Calls to REST / gRPC

When two modules *inside* the legacy WebLogic monolith communicated via SOAP (or
when decomposing two tightly coupled microservices), eliminate the XML/SOAP
overhead by refactoring the internal contract to REST/JSON or gRPC.

### Strategy A: Convert to REST / JSON (`@RestController`)

Replace `@WebService` with Spring `@RestController` or Quarkus JAX-RS `@Path`,
converting XML payloads to lightweight JSON DTOs:

```java
// Spring Boot REST Controller Replacement
@RestController
@RequestMapping("/api/v1/patients")
public class PatientLookupRestController {
    @Autowired
    private PatientService patientService;

    @GetMapping("/ssn/{ssn}")
    public ResponseEntity<PatientRecordDTO> getPatientBySSN(@PathVariable String ssn) {
        return ResponseEntity.ok(patientService.getPatientBySSN(ssn));
    }
}
```

### Strategy B: Convert to gRPC / Protocol Buffers (High-Performance Internal RPC)

For high-frequency internal calls across Cloud Run VPC networks, define a
`.proto` schema:

```protobuf
syntax = "proto3";
package medimed.patient;

service PatientLookupService {
    rpc GetPatientBySSN (PatientRequest) returns (PatientRecord);
}

message PatientRequest {
    string ssn = 1;
}

message PatientRecord {
    int64 id = 1;
    string name = 2;
    string dob = 3;
}
```

--------------------------------------------------------------------------------

## 3. WS-Security to Cloud IAM & OIDC Bearer Tokens

Legacy WebLogic SOAP services often used WS-Security (e.g., UsernameToken
profiles or SAML assertions inside XML SOAP headers) configured via WebLogic
policies (`weblogic.wsee.security.*`).

### After: API Gateway & OIDC Bearer Token Modernization

In cloud-native GCP architectures, strip WS-Security encryption/authentication
from the application layer:

1.  **Transport Security**: Terminate TLS/HTTPS at Google Cloud Load Balancing
    or Google Cloud API Gateway (Apigee / Cloud Endpoints).
2.  **Authentication / Authorization**: Require clients to pass standard RFC
    6750 OAuth2 / OIDC **Bearer Tokens** in the HTTP Authorization header
    (`Authorization: Bearer <jwt>`).
3.  **Service Validation**: Use Spring Security OAuth2 Resource Server or
    Quarkus OIDC to validate the JWT signature and enforce role claims
    (`@PreAuthorize` / `@RolesAllowed`) before invoking the SOAP endpoint
    implementor.
