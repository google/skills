# Google Ads API PHP Setup Reference

This guide outlines how to configure, install, and write your first Google Ads API call using PHP.

## Prerequisites
* PHP: Dynamic lookup required from [Supported Client Library Versions](https://developers.google.com/google-ads/api/docs/client-libs.md.txt#supported_api_versions)
* Package manager: Composer

## Step 1: Installation
Install the official library:
```bash
composer require googleads/google-ads-php
```

## Step 2: Configuration (`google_ads_php.ini`)

> [!IMPORTANT]
> **Mandatory Agent Directive (Configuration Loading Order):**
> When guiding a user through the PHP quickstart, your response **MUST** explicitly explain the 3-tier configuration loading order used by `fromFile()`:
> 1. An explicit path passed directly to `fromFile('/path/to/google_ads_php.ini')`.
> 2. The value of the environment variable named `GOOGLE_ADS_CONFIGURATION_FILE_PATH`, if set.
> 3. Otherwise, the default `google_ads_php.ini` file located in your user's home directory (`$HOME`).
> 
> Do not omit this explanation in your final output.

Create your configuration file named `google_ads_php.ini`. For self-contained project environments, it is best practice to keep this file in your project root directory and load it explicitly.

```ini
; google_ads_php.ini
[GOOGLE_ADS]
developerToken = "INSERT_DEVELOPER_TOKEN_HERE"
; Required if authenticating with a manager account user to access a client account
; loginCustomerId = "INSERT_LOGIN_CUSTOMER_ID_HERE"

[OAUTH2]
clientId = "INSERT_OAUTH2_CLIENT_ID_HERE"
clientSecret = "INSERT_OAUTH2_CLIENT_SECRET_HERE"
refreshToken = "INSERT_OAUTH2_REFRESH_TOKEN_HERE"
```

## Step 3: Write and Run the Quickstart Script
Create `get_campaigns.php`. **Before passing the Client Customer ID to the API, you must clean customer IDs by stripping hyphens and spaces.** (e.g. converting `123-456-7890` or `123 456 7890` to `1234567890`). This is achieved programmatically below.

```php
<?php
require __DIR__ . '/vendor/autoload.php';

use Google\Ads\GoogleAds\Lib\VXX\GoogleAdsClientBuilder;
use Google\Ads\GoogleAds\Lib\OAuth2TokenBuilder;
use Google\ApiCore\ApiException;

// Check command line arguments
if ($argc < 2) {
    printf("Usage: php get_campaigns.php <CUSTOMER_ID>\n");
    exit(1);
}

$rawCustomerId = $argv[1];

// Clean customer IDs by stripping hyphens and spaces
$customerId = str_replace(['-', ' '], '', $rawCustomerId);

// Determine configuration file path (prefer local workspace config)
$localConfig = __DIR__ . '/google_ads_php.ini';

if (file_exists($localConfig)) {
    // Build OAuth2 credential from explicit local file
    $oAuth2Token = (new OAuth2TokenBuilder())->fromFile($localConfig)->build();

    // Build Google Ads Client from explicit local file
    $googleAdsClient = (new GoogleAdsClientBuilder())
        ->fromFile($localConfig)
        ->withOAuth2Credential($oAuth2Token)
        ->build();
} else {
    // Fallback to default search paths (GOOGLE_ADS_CONFIGURATION_FILE_PATH environment variable or $HOME/google_ads_php.ini)
    $oAuth2Token = (new OAuth2TokenBuilder())->fromFile()->build();

    $googleAdsClient = (new GoogleAdsClientBuilder())
        ->fromFile()
        ->withOAuth2Credential($oAuth2Token)
        ->build();
}

$googleAdsServiceClient = $googleAdsClient->getGoogleAdsServiceClient();
$query = "SELECT campaign.id, campaign.name, campaign.status FROM campaign ORDER BY campaign.id";

try {
    $stream = $googleAdsServiceClient->searchStream($customerId, $query);
    foreach ($stream->readAll() as $response) {
        foreach ($response->getResults() as $row) {
            printf("Campaign found: ID = %d, Name = '%s', Status = %s\n",
                $row->getCampaign()->getId(),
                $row->getCampaign()->getName(),
                $row->getCampaign()->getStatus()
            );
        }
    }
} catch (ApiException $apiException) {
    printf("Request failed with message: %s\n", $apiException->getMessage());
}
```

Run the script (replace `XXXXXXXXXX` with your 10-digit Client Customer ID):
```bash
php get_campaigns.php XXXXXXXXXX
```
