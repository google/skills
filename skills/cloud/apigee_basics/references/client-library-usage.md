# Apigee Client Library Usage

You can programmatically manage Apigee organizations, environments, proxies, and
products using Google's official client libraries. This document provides basic
integration examples in **Python**, **Node.js**, **Go**, and **Java**.

The Apigee Management API in client libraries uses the service endpoint
`apigee.googleapis.com`.

--------------------------------------------------------------------------------

## 1. Python

Ensure the Google API Client library is installed:

```bash
pip install google-api-python-client google-auth
```

### Code Snippet: List API Proxies

```python
import google.auth
from googleapiclient import discovery

# Authenticate and construct the Apigee client service
credentials, project = google.auth.default()
service = discovery.build('apigee', 'v1', credentials=credentials)

org_name = "your-apigee-org"
parent = f"organizations/{org_name}"

try:
    # Invoke the APIs list endpoint
    request = service.organizations().apis().list(parent=parent)
    response = request.execute()

    proxies = response.get('proxies', [])
    print("API Proxies configured in Organization:")
    for proxy in proxies:
        print(f"- {proxy.get('name')}")
except Exception as e:
    print(f"Error calling Apigee API: {e}")
```

--------------------------------------------------------------------------------

## 2. Node.js

Ensure the Google APIs package is installed:

```bash
npm install googleapis
```

### Code Snippet: List API Proxies

```javascript
const { google } = require('googleapis');

async function listProxies() {
  const orgName = 'your-apigee-org';

  // Authenticate using Application Default Credentials
  const auth = new google.auth.GoogleAuth({
    scopes: ['https://www.googleapis.com/auth/cloud-platform']
  });
  const authClient = await auth.getClient();

  const apigee = google.apigee({
    version: 'v1',
    auth: authClient
  });

  try {
    const res = await apigee.organizations.apis.list({
      parent: `organizations/${orgName}`
    });

    const proxies = res.data.proxies || [];
    console.log('API Proxies configured in Organization:');
    proxies.forEach(proxy => {
      console.log(`- ${proxy.name}`);
    });
  } catch (err) {
    console.error('Error calling Apigee API:', err);
  }
}

listProxies();
```

--------------------------------------------------------------------------------

## 3. Go

Ensure the Go Apigee package is added:

```bash
go get google.golang.org/api/apigee/v1
```

### Code Snippet: List API Proxies

```go
package main

import (
    "context"
    "fmt"
    "log"

    "google.golang.org/api/apigee/v1"
)

func main() {
    ctx := context.Background()
    orgName := "your-apigee-org"

    // Initialize the Apigee service using default credentials
    apigeeService, err := apigee.NewService(ctx)
    if err != nil {
        log.Fatalf("Failed to initialize Apigee service: %v", err)
    }

    parent := fmt.Sprintf("organizations/%s", orgName)
    call := apigeeService.Organizations.Apis.List(parent)

    response, err := call.Do()
    if err != nil {
        log.Fatalf("Failed to list API proxies: %v", err)
    }

    fmt.Println("API Proxies configured in Organization:")
    for _, proxy := range response.Proxies {
        fmt.Printf("- %s\n", proxy.Name)
    }
}
```

--------------------------------------------------------------------------------

## 4. Java

Ensure the following dependencies are included in your `pom.xml` file:

```xml
<dependency>
    <groupId>com.google.apis</groupId>
    <artifactId>google-api-services-apigee</artifactId>
    <version>v1-rev20240124-2.0.0</version> <!-- Use latest version -->
</dependency>
```

### Code Snippet: List API Proxies

```java
import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport;
import com.google.api.client.json.gson.GsonFactory;
import com.google.api.services.apigee.v1.Apigee;
import com.google.api.services.apigee.v1.model.GoogleCloudApigeeV1ListApiProxiesResponse;
import com.google.api.services.apigee.v1.model.GoogleCloudApigeeV1ApiProxy;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.http.HttpCredentialsAdapter;

import java.io.IOException;
import java.security.GeneralSecurityException;

public class ApigeeListProxies {
    public static void main(String[] args) {
        String orgName = "your-apigee-org";
        String parent = "organizations/" + orgName;

        try {
            // Load Default Credentials
            GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();
            HttpCredentialsAdapter requestInitializer = new HttpCredentialsAdapter(credentials);

            // Initialize the Apigee service
            Apigee apigeeService = new Apigee.Builder(
                    GoogleNetHttpTransport.newTrustedTransport(),
                    GsonFactory.getDefaultInstance(),
                    requestInitializer)
                    .setApplicationName("apigee-basics-skill")
                    .build();

            GoogleCloudApigeeV1ListApiProxiesResponse response = apigeeService.organizations()
                    .apis()
                    .list(parent)
                    .execute();

            System.out.println("API Proxies configured in Organization:");
            if (response.getProxies() != null) {
                for (GoogleCloudApigeeV1ApiProxy proxy : response.getProxies()) {
                    System.out.println("- " + proxy.getName());
                }
            }
        } catch (IOException | GeneralSecurityException e) {
            System.err.println("Error calling Apigee API: " + e.getMessage());
        }
    }
}
```
