# Google Ads API .NET Setup Reference

This guide outlines how to configure, install, and write your first Google Ads API call using .NET/C#.

## Prerequisites
* .NET SDK: Dynamic lookup required from [Supported Client Library Versions](https://developers.google.com/google-ads/api/docs/client-libs.md.txt#supported_api_versions)
* Package manager: NuGet

## Step 1: Installation
Install the official package using NuGet:
```bash
dotnet add package Google.Ads.GoogleAds
```

## Step 2: Configuration (Runtime Initialization)
The preferred way to configure the .NET client library is to initialize a `GoogleAdsConfig` object at runtime. Gather your required credentials to include in your code:
* Developer Token
* OAuth2 Client ID
* OAuth2 Client Secret
* OAuth2 Refresh Token
* Login Customer ID (optional, required if authenticating as a manager account)

### Alternate Configuration Options
If you prefer external configuration files or environment variables, add a NuGet reference to the `Google.Ads.GoogleAds.Extensions` package. You must then explicitly load the settings onto your `GoogleAdsConfig` object:
* **Environment Variables:** Call `config.LoadFromEnvironmentVariables()`.
* **App.config:** Call `config.LoadFromDefaultAppConfigSection()`.
* **settings.json / Custom JSON:** Use `ConfigurationBuilder` and call `config.LoadFromConfigurationRoot(configRoot)`.

## Step 3: Write and Run the Quickstart Script
Create `Program.cs`. **Before passing the Client Customer ID to the API, you must clean customer IDs by stripping hyphens (e.g., converting `123-456-7890` to `1234567890`).** This ensures standard numeric parsing:

**IMPORTANT**

Replace VXX and VXX in the namespace and service calls with the latest supported version (e.g., V24) discovered in the Prerequisites step.

```csharp
using System;
using Google.Ads.GoogleAds.Config;
using Google.Ads.GoogleAds.Lib;
using Google.Ads.GoogleAds.VXX.Services;
using Google.Ads.GoogleAds.VXX.Errors;

class Program {
    static void Main(string[] args) {
        if (args.Length < 1) {
            Console.WriteLine("Usage: dotnet run <CUSTOMER_ID>");
            return;
        }

        // Clean customer ID by stripping hyphens
        string customerId = args[0].Replace("-", "");
        
        GoogleAdsConfig config = new GoogleAdsConfig()
        {
            DeveloperToken = "INSERT_DEVELOPER_TOKEN_HERE",
            OAuth2Mode = OAuth2Flow.APPLICATION,
            OAuth2ClientId = "INSERT_OAUTH2_CLIENT_ID_HERE",
            OAuth2ClientSecret = "INSERT_OAUTH2_CLIENT_SECRET_HERE",
            OAuth2RefreshToken = "INSERT_OAUTH2_REFRESH_TOKEN_HERE",
            // LoginCustomerId = "INSERT_LOGIN_CUSTOMER_ID_HERE"
        };

        // Optional: If using Google.Ads.GoogleAds.Extensions, you can also load overriding environment variables:
        // config.LoadFromEnvironmentVariables();

        GoogleAdsClient client = new GoogleAdsClient(config);
        GoogleAdsServiceClient service = client.GetService(Services.VXX.GoogleAdsService);
        string query = "SELECT campaign.id, campaign.name, campaign.status FROM campaign ORDER BY campaign.id";

        try {
            service.SearchStream(customerId, query, delegate(SearchGoogleAdsStreamResponse response) {
                foreach (GoogleAdsRow row in response.Results) {
                    Console.WriteLine($"Campaign found: ID = {row.Campaign.Id}, Name = '{row.Campaign.Name}', Status = {row.Campaign.Status}");
                }
            });
        } catch (GoogleAdsException ex) {
            Console.WriteLine($"Request failed: ID {ex.RequestId}. Error: {ex.Message}");
        }
    }
}
```

Run the project (replace `XXXXXXXXXX` with your 10-digit Client Customer ID):
```bash
dotnet run XXXXXXXXXX
```

## Step 4: Verification

Verify the output of your run. A successful execution will stream the campaigns associated with the customer ID to the console, similar to the following:

```text
Campaign found: ID = 987654321, Name = 'Interstate Search Promo', Status = Enabled
Campaign found: ID = 555444333, Name = 'Local Brand Awareness', Status = Paused
```
