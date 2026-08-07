# .NET Client and Utility Library Installation

## Install Client Library

Install the `Google.Ads.DataManager.V1` NuGet package:

```shell
dotnet add package Google.Ads.DataManager.V1
```

## Install Utility Library

> [!IMPORTANT]
> The companion utility libraries are not available on public package managers
> (such as NuGet). Follow the instructions below to clone and install the
> library.

1.  Clone the repository:
    ```shell
    git clone https://github.com/googleads/data-manager-dotnet.git
    ```
2.  In your .NET project, declare a `ProjectReference` dependency pointing to
    the cloned library's `.csproj` path (replacing `{path_to_utility_library}`
    with the local path of the cloned repository):
    ```xml
    <ProjectReference Include="{path_to_utility_library}\Google.Ads.DataManager.Util\src\Google.Ads.DataManager.Util.csproj" />
    ```
