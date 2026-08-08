# WebLogic Legacy Remoting & JCA (Java Connector Architecture) Modernization Guide

This guide provides concrete transformation recipes for modernizing legacy
WebLogic remoting protocols (T3, RMI, CORBA/IIOP, EJB 2.x Remote Home
interfaces) and JCA Resource Adapters (`.rar`) when migrating to cloud-native
serverless microservices on GCP (Spring Boot or Quarkus on Cloud Run or Cloud
Functions).

## Table of Contents

*   [1. Legacy Remoting: T3 Protocol, RMI/IIOP, & EJB 2.x Remote Homes](#1-legacy-remoting-t3-protocol-rmiiiop--ejb-2x-remote-homes) (Line 16)
*   [2. JCA (Java Connector Architecture) & Mainframe Resource Adapters (.rar)](#2-jca-java-connector-architecture--mainframe-resource-adapters-rar) (Line 137)

--------------------------------------------------------------------------------

## 1. Legacy Remoting: T3 Protocol, RMI/IIOP, & EJB 2.x Remote Homes

In legacy WebLogic multi-JVM architectures, clients and server components
communicate across network boundaries using WebLogic's specific T3 protocol
(`t3://`) or RMI over IIOP.

### Before: Legacy WebLogic Remoting Pattern

Clients perform JNDI lookups using specific initial context factories and
provider URLs, casting results to remote EJB home interfaces that throw
`java.rmi.RemoteException`:

```java
// Legacy WebLogic T3 / RMI EJB Client Lookup
Properties props = new Properties();
props.put(Context.INITIAL_CONTEXT_FACTORY, "weblogic.jndi.WLInitialContextFactory");
props.put(Context.PROVIDER_URL, "t3://weblogic-prod-01:7001,weblogic-prod-02:7001");

InitialContext ctx = new InitialContext(props);
Object obj = ctx.lookup("ejb/PatientRecordRemoteHome");
PatientRecordHome home = (PatientRecordHome) PortableRemoteObject.narrow(obj, PatientRecordHome.class);
PatientRecord remoteEJB = home.create();

try {
    PatientDTO patient = remoteEJB.getPatientDetails(1042L);
} catch (RemoteException re) {
    // Handle network / RMI failure
}
```

### After: Cloud-Native REST & gRPC Modernization on GCP

In a cloud-native serverless environment (GKE / Cloud Run / Cloud Functions),
proprietary binary protocols like T3 and RMI/IIOP are blocked by modern HTTP
load balancers and firewalls. All inter-service communication must be decoupled
into stateless HTTP/S protocols.

#### Strategy A: REST over HTTPS with JSON Payloads (Recommended for general microservices)

1.  **Server Side (Target Microservice)**: Rewrite the Remote EJB interface and
    implementation into a stateless REST controller:

    *   **Spring Boot**:

        ```java
        @RestController
        @RequestMapping("/api/v1/patients")
        public class PatientRecordController {
            @Autowired
            private PatientService patientService;

            @GetMapping("/{id}")
            public ResponseEntity<PatientDTO> getPatientDetails(@PathVariable Long id) {
                return ResponseEntity.ok(patientService.getPatientDetails(id));
            }
        }
        ```

    *   **Quarkus (JAX-RS)**:

        ```java
        @Path("/api/v1/patients")
        @Produces(MediaType.APPLICATION_JSON)
        public class PatientRecordResource {
            @Inject
            PatientService patientService;

            @GET
            @Path("/{id}")
            public PatientDTO getPatientDetails(@PathParam("id") Long id) {
                return patientService.getPatientDetails(id);
            }
        }
        ```

2.  **Client Side (Calling Microservice)**: Replace
    `InitialContext.lookup("t3://...")` and `RemoteException` handling with
    declarative HTTP clients or `RestClient`:

    *   **Spring Boot (Spring Cloud OpenFeign or RestClient)**:

        ```java
        @Service
        public class BillingService {
            @Autowired
            private RestClient patientRestClient; // Configured with target Cloud Run service URL

            public void processBilling(Long patientId) {
                try {
                    PatientDTO patient = patientRestClient.get()
                        .uri("/api/v1/patients/{id}", patientId)
                        .retrieve()
                        .body(PatientDTO.class);
                } catch (RestClientResponseException ex) {
                    // Handle HTTP error status codes (404 Not Found, 503 Service Unavailable) instead of RemoteException
                }
            }
        }
        ```

    *   **Quarkus (MicroProfile Rest Client)**:

        ```java
        @RegisterRestClient(configKey = "patient-api")
        @Path("/api/v1/patients")
        public interface PatientClient {
            @GET
            @Path("/{id}")
            PatientDTO getPatientDetails(@PathParam("id") Long id);
        }
        ```

#### Strategy B: gRPC over HTTP/2 (Recommended for ultra-high performance internal RPCs)

When legacy RMI was used for high-frequency, low-latency internal binary
messaging between tightly coupled backend modules, map the remote interface to a
Protocol Buffers (`.proto`) schema and deploy gRPC services over Cloud Run
internal VPC networks.

--------------------------------------------------------------------------------

## 2. JCA (Java Connector Architecture) & Mainframe Resource Adapters (`.rar`)

Enterprise WebLogic monoliths in banking and insurance frequently connect to
legacy mainframe systems (CICS, IMS, AS/400, SAP) or proprietary ERPs using JCA
Resource Adapters deployed as `.rar` archives in WebLogic, interacting via
`javax.resource.cci.*` (Common Client Interface).

### Before: Legacy WebLogic JCA / CCI Pattern

```java
// Legacy WebLogic JCA CCI Lookup
InitialContext ctx = new InitialContext();
ConnectionFactory cf = (ConnectionFactory) ctx.lookup("eis/CicsMainframeAdapter");
Connection conn = cf.getConnection();
Interaction interaction = conn.createInteraction();

CicsRecordInput input = new CicsRecordInput("TXN_8842");
CicsRecordOutput output = new CicsRecordOutput();

// Execute synchronous mainframe transaction over JCA adapter
interaction.execute(null, input, output);
conn.close();
```

### After: Cloud-Native Mainframe Integration on GCP

In serverless container environments (Cloud Run / Cloud Functions), deploying
embedded JCA `.rar` resource adapters is unsupported and anti-pattern.

#### Strategy 1: Google Cloud Integration Connectors (Apigee / Application Integration)

Instead of embedding mainframe proprietary drivers directly inside microservice
containers, offload legacy EIS connectivity to **Google Cloud Integration
Connectors** or **Apigee Mainframe Adapters**:

1.  Configure an Integration Connector resource in GCP pointing to the
    CICS/IMS/SAP mainframe endpoint.
2.  Refactor the microservice code to make a standard REST API call or gRPC
    invocation to the Integration Connector endpoint.

```java
// Cloud-Native Mainframe Invocation via GCP Integration Connector / REST Proxy
@Service
public class MainframeIntegrationService {
    @Autowired
    private RestClient gcpConnectorClient;

    public CicsResponse executeTransaction(String txnId) {
        return gcpConnectorClient.post()
            .uri("/v1/projects/my-project/locations/us-central1/connections/cics-connector:execute")
            .body(new CicsRequest(txnId))
            .retrieve()
            .body(CicsResponse.class);
    }
}
```

#### Strategy 2: Asynchronous Mainframe Messaging over GCP Pub/Sub

If the legacy JCA adapter was used for inbound message listening or asynchronous
transaction processing:

1.  Re-route mainframe outbound queues (e.g., IBM MQ or Mainframe Event Streams)
    into **Google Cloud Pub/Sub topics** (via Google Cloud Pub/Sub Connector or
    Kafka Bridge).
2.  Replace JCA message listeners in the microservice with standard **Spring
    Cloud GCP Pub/Sub `@GcpPubSubSubscription` listeners** or **Quarkus Reactive
    Messaging `@Incoming` annotations**.
