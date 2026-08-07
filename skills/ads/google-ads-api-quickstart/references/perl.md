# Google Ads API Perl Setup Reference

This guide outlines how to configure, install, and write your first Google Ads API call using Perl.

## Prerequisites
* Perl: Dynamic lookup required from [Supported Client Library Versions](https://developers.google.com/google-ads/api/docs/client-libs.md.txt#supported_api_versions)
* CPAN client: `cpanm`

## Step 1: Installation
Install the library:
```bash
cpanm Google::Ads::GoogleAds::Client
```

## Step 2: Configuration (`googleads.properties`)
Create your configuration file named `googleads.properties`.

When instantiating the client via `Client->new()`, the Perl client library resolves the configuration file path in the following order:
1. An explicit path passed directly to `Client->new({properties_file => '/path/to/googleads.properties'})`.
2. The location specified in the `GOOGLE_ADS_CONFIGURATION_FILE_PATH` environment variable, if set.
3. Otherwise, the default `googleads.properties` file located in your user's home directory (`$HOME`).

For self-contained project environments, it is best practice to keep this file in your project root directory and load it explicitly.

```properties
# googleads.properties
developer_token=INSERT_DEVELOPER_TOKEN_HERE
client_id=INSERT_OAUTH2_CLIENT_ID_HERE
client_secret=INSERT_OAUTH2_CLIENT_SECRET_HERE
refresh_token=INSERT_OAUTH2_REFRESH_TOKEN_HERE
# login_customer_id=INSERT_LOGIN_CUSTOMER_ID_HERE
```

## Step 3: Write and Run the Quickstart Script
Create `get_campaigns.pl`:
```perl
use strict;
use warnings;
use Google::Ads::GoogleAds::Client;
use Google::Ads::GoogleAds::Utils::SearchStreamHandler;

my $customer_id = $ARGV[0];
$customer_id =~ s/-//g;

# Determine configuration file path (prefer local workspace config)
my $local_config = "./googleads.properties";
my $client;

if (-e $local_config) {
    # Load explicitly from local workspace
    $client = Google::Ads::GoogleAds::Client->new({properties_file => $local_config});
} else {
    # Fallback to default search paths (GOOGLE_ADS_CONFIGURATION_FILE_PATH environment variable or $HOME/googleads.properties)
    $client = Google::Ads::GoogleAds::Client->new();
}

# Load any overriding configuration from environment variables
$client->configure_from_environment_variables();

my $query = "SELECT campaign.id, campaign.name, campaign.status FROM campaign ORDER BY campaign.id";

my $search_stream_handler = Google::Ads::GoogleAds::Utils::SearchStreamHandler->new({
    client => $client,
    customer_id => $customer_id,
    query => $query
});

$search_stream_handler->process(sub {
    my $row = shift;
    printf "Campaign found: ID = %s, Name = '%s', Status = %s\n",
        $row->{campaign}{id},
        $row->{campaign}{name},
        $row->{campaign}{status};
});
```

Run the script (replace `XXXXXXXXXX` with your 10-digit Client Customer ID):
```bash
perl get_campaigns.pl XXXXXXXXXX
```
