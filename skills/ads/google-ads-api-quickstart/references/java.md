# Google Ads API Java Setup Reference

This guide outlines how to configure, install, and write your first Google Ads API call using Java.

## Prerequisites

*   **Java Development Kit (JDK):** Version 1.8 or higher. Dynamic lookup of the minimum required version is recommended from the [Supported Client Library Versions](https://developers.google.com/google-ads/api/docs/client-libs.md.txt#supported_api_versions).
*   **Build Tool:** Maven or Gradle.

---

## Step 1: Installation & Dependency Management

You must add the Google Ads Client Library to your project. 

> [!IMPORTANT]
> **Action Required:** Before adding the dependency, you must look up the latest release version from the [Google Ads Java Library GitHub Releases](https://github.com/googleads/google-ads-java/releases) and replace `LATEST_LIBRARY_VERSION` below with the actual version number (e.g., `33.0.0`).

### Option A: Maven (`pom.xml`)
Add the following to your `<dependencies>` section:
```xml
<dependency>
  <groupId>com.google.api-ads</groupId>
  <artifactId>google-ads</artifactId>
  <version>LATEST_LIBRARY_VERSION</version>
</dependency>
```

### Option B: Gradle (`build.gradle`)
Add the following to your `dependencies` block:
```groovy
implementation 'com.google.api-ads:google-ads:LATEST_LIBRARY_VERSION'
```

---

## Step 2: Configuration (`ads.properties`)

> [!IMPORTANT]
> **Mandatory Agent Directive (Configuration Loading Mechanisms):**
> When guiding a user through the Java quickstart, your response **MUST** explicitly explain the configuration loading mechanisms and lookup hierarchy used by `fromPropertiesFile()`:
> 1. An explicit path passed directly to `fromPropertiesFile(PATH_TO_CONFIG_FILE)`.
> 2. The location specified in the `GOOGLE_ADS_CONFIGURATION_FILE_PATH` environment variable, if set.
> 3. Otherwise, the default `ads.properties` file located in your user's home directory (`System.getProperty("user.home") + "/ads.properties"`) or on the classpath.
> 
> Do not omit this explanation in your final output.

Create a configuration file named `ads.properties`.

You can also configure the client library using environment variables (e.g., `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`) via `fromEnvironment()`, or combine both approaches.

> [!TIP]
> **File Location:** For Maven/Gradle projects, the best place to put this file is in the resources directory: `src/main/resources/ads.properties`. This ensures it is automatically included in the classpath.

Populate the file with your credentials:
```properties
api.googleads.developerToken=INSERT_DEVELOPER_TOKEN_HERE
api.googleads.clientId=INSERT_OAUTH2_CLIENT_ID_HERE
api.googleads.clientSecret=INSERT_OAUTH2_CLIENT_SECRET_HERE
api.googleads.refreshToken=INSERT_OAUTH2_REFRESH_TOKEN_HERE
# Optional: Un-comment if you are accessing a client account through a manager account
# api.googleads.loginCustomerId=INSERT_LOGIN_CUSTOMER_ID_HERE
```

---

## Step 3: Write the Quickstart Script

Create a file named `GetCampaigns.java`. 

> [!IMPORTANT]
> **Rule 1: Normalize Customer IDs**
> Before passing the Client Customer ID to the API, you **must** normalize it by stripping all hyphens (e.g., converting `123-456-7890` to `1234567890`). Failing to do so will cause API validation errors.
>
> **Rule 2: Resolve Package Versions (`vXX`)**
> The imports below contain a placeholder `vXX`. You **must** replace `vXX` with the specific API version you are targeting (matching the library version installed in Step 1). For example, if using library v33.0.0, the API version is likely `v24` (packages will be `com.google.ads.googleads.v24.services...`).

```java
import com.google.ads.googleads.lib.GoogleAdsClient;
// IMPORTANT: Replace vXX with the active API version (e.g., v24)
import com.google.ads.googleads.vXX.services.GoogleAdsServiceClient;
import com.google.ads.googleads.vXX.services.SearchGoogleAdsStreamRequest;
import com.google.ads.googleads.vXX.services.SearchGoogleAdsStreamResponse;
import com.google.ads.googleads.vXX.errors.GoogleAdsException;
import java.io.IOException;

public class GetCampaigns {
    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("Usage: java GetCampaigns <CUSTOMER_ID>");
            System.exit(1);
        }

        // Normalize customer ID by removing hyphens
        String customerId = args[0].replace("-", "");
        
        GoogleAdsClient googleAdsClient;
        try {
            // Combines environment variables (fromEnvironment) and classpath/home configuration (fromPropertiesFile)
            googleAdsClient = GoogleAdsClient.newBuilder()
                    .fromEnvironment()
                    .fromPropertiesFile()
                    .build();
        } catch (IOException e) {
            System.err.println("Failed to load configuration. Ensure ads.properties is in src/main/resources/ or environment variables are set.");
            e.printStackTrace();
            System.exit(1);
            return;
        }

        // The try-with-resources block ensures the gRPC client channel is closed automatically
        try (GoogleAdsServiceClient googleAdsServiceClient = googleAdsClient.getLatestVersion().createGoogleAdsServiceClient()) {
            
            String query = "SELECT campaign.id, campaign.name, campaign.status FROM campaign ORDER BY campaign.id";
            
            SearchGoogleAdsStreamRequest request = SearchGoogleAdsStreamRequest.newBuilder()
                    .setCustomerId(customerId)
                    .setQuery(query)
                    .build();

            System.out.println("Querying Google Ads API...");
            
            // Execute the stream request
            googleAdsServiceClient.searchStreamCallable().call(request).forEach(response -> {
                response.getResultsList().forEach(row -> {
                    System.out.printf("Campaign found: ID = %d, Name = '%s', Status = %s%n",
                            row.getCampaign().getId(),
                            row.getCampaign().getName(),
                            row.getCampaign().getStatus().name());
                });
            });
        } catch (GoogleAdsException gae) {
            System.err.printf("Request ID %s failed.%n", gae.getRequestId());
            System.err.printf("Error details: %s%n", gae.getMessage());
            System.exit(1);
        }
    }
}
```

---

## Step 4: Compile and Run

Do not run the file in isolation if it relies on Maven/Gradle dependencies. Use your build tool to compile and execute the application to ensure the classpath is correctly configured.

### Using Maven
Run the following command from the project root:
```bash
mvn compile exec:java -Dexec.mainClass="GetCampaigns" -Dexec.args="XXXXXXXXXX"
```

### Using Gradle
If using the Gradle Application plugin, run:
```bash
./gradlew run --args="XXXXXXXXXX"
```
*(Replace `XXXXXXXXXX` with your 10-digit customer ID, with or without hyphens).*

---

## Step 5: Verification & Troubleshooting

### Expected Success Output
Upon successful execution, you should see output similar to the following:
```text
Querying Google Ads API...
Campaign found: ID = 123456789, Name = 'Search - Brand - US', Status = ENABLED
Campaign found: ID = 987654321, Name = 'Display - Remarketing', Status = PAUSED
```

### Common Errors

| Error Symptom / Code | Root Cause | Solution |
| :--- | :--- | :--- |
| `FileNotFoundException: ads.properties` | The library cannot find the configuration file. | Ensure `ads.properties` is placed in `src/main/resources/` (Maven/Gradle) or explicitly set the path using the `api.googleads.configurationFilePath` system property. |
| `DEVELOPER_TOKEN_NOT_APPROVED` | You are using an unapproved ("Pending") developer token against a production account (production calls require Explorer, Basic, or Standard Access). | Use a **Test Account** (which allows pending tokens) or wait for token approval. |
| `NOT_ADS_USER` | The OAuth2 user credentials used to generate the refresh token do not have access to the specified `CUSTOMER_ID`. | Re-authenticate the OAuth2 flow using a Google account that has access to the target Ads account. |
| `INVALID_CUSTOMER_ID` | The customer ID passed was not numeric (e.g., it still contained hyphens, or was the wrong length). | Verify that the normalization code `args[0].replace("-", "")` executed successfully. |
