# Google Ads API Ruby Setup Reference

This guide outlines how to configure, install, and write your first Google Ads API call using Ruby.

## Prerequisites
* Ruby: Dynamic lookup required from [Supported Client Library Versions](https://developers.google.com/google-ads/api/docs/client-libs.md.txt#supported_api_versions)
* Package manager: RubyGems

## Step 1: Installation
To get started with the client library, **you must install the gem: `gem install google-ads-googleads`.** Run this command directly in your terminal:
```bash
gem install google-ads-googleads
```

## Step 2: Configuration (`google_ads_config.rb`)

> [!IMPORTANT]
> **Mandatory Agent Directive (Configuration Loading Order):**
> When guiding a user through the Ruby quickstart, your response **MUST** explicitly explain the 3-tier configuration loading order used by `GoogleAdsClient.new`:
> 1. An explicit path passed directly to the constructor: `GoogleAdsClient.new('/path/to/google_ads_config.rb')`.
> 2. The location specified in the `GOOGLE_ADS_CONFIGURATION_FILE_PATH` environment variable, if set.
> 3. Otherwise, the default `google_ads_config.rb` file located in your user's home directory (`$HOME`).
> 
> Do not omit this explanation in your final output.

Create your configuration file named `google_ads_config.rb`. For self-contained project environments, it is best practice to keep this file in your project root directory and load it explicitly.

```ruby
# google_ads_config.rb
Google::Ads::GoogleAds::Config.new do |c|
  c.developer_token = 'INSERT_DEVELOPER_TOKEN_HERE'
  c.client_id = 'INSERT_OAUTH2_CLIENT_ID_HERE'
  c.client_secret = 'INSERT_OAUTH2_CLIENT_SECRET_HERE'
  c.refresh_token = 'INSERT_OAUTH2_REFRESH_TOKEN_HERE'
  # Optional: Required if authenticating with a manager account user to access a client account
  # c.login_customer_id = 'INSERT_LOGIN_CUSTOMER_ID_HERE'
end
```

## Step 3: Write and Run the Quickstart Script
Create `get_campaigns.rb`. **Before passing the Client Customer ID to the API, you must clean customer IDs by removing hyphens (e.g. converting `123-456-7890` to `1234567890`).**

Below is the complete, self-contained Ruby source code to clean the ID and retrieve campaign details:

```ruby
require 'google/ads/google_ads'

if ARGV.empty?
  puts "Usage: ruby get_campaigns.rb <CUSTOMER_ID>"
  exit 1
end

# Clean customer ID by removing hyphens
customer_id = ARGV[0].gsub('-', '')

# Determine configuration file path (prefer local workspace config)
local_config = File.expand_path('google_ads_config.rb', __dir__)

client = if File.exist?(local_config)
           # Load explicitly from local workspace
           Google::Ads::GoogleAds::GoogleAdsClient.new(local_config)
         else
           # Fallback to default search paths (GOOGLE_ADS_CONFIGURATION_FILE_PATH environment variable or $HOME/google_ads_config.rb)
           Google::Ads::GoogleAds::GoogleAdsClient.new
         end

query = "SELECT campaign.id, campaign.name, campaign.status FROM campaign ORDER BY campaign.id"

begin
  response = client.service.google_ads.search_stream(
    customer_id: customer_id,
    query: query,
  )
  response.each do |page|
    page.results.each do |row|
      puts "Campaign found: ID = #{row.campaign.id}, Name = '#{row.campaign.name}', Status = #{row.campaign.status}"
    end
  end
rescue Google::Ads::GoogleAds::Errors::GoogleAdsError => e
  e.failure.errors.each do |error|
    puts "Error: #{error.message}"
  end
end
```

Run the script (replace `XXXXXXXXXX` with your 10-digit Client Customer ID):
```bash
ruby get_campaigns.rb XXXXXXXXXX
```
