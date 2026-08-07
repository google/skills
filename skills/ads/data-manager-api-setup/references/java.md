# Java Client and Utility Library Installation

## Install Client Library

Determine the latest version of `com.google.api-ads:data-manager` by running:
```shell
curl -s "https://repo1.maven.org/maven2/com/google/api-ads/data-manager/maven-metadata.xml" \
  | grep -Po '(?<=<release>)[^<]+'
```

If using Maven, add the following dependency to your `pom.xml` file.
Replace `{latest_version}` with the version retrieved above:

```xml
<dependency>
  <groupId>com.google.api-ads</groupId>
  <artifactId>data-manager</artifactId>
  <version>{latest_version}</version>
</dependency>
```

If using Gradle, add this to your dependencies.
Replace `{latest_version}` with the version retrieved above:

```groovy
implementation 'com.google.api-ads:data-manager:{latest_version}'
```

## Install Utility Library

> [!IMPORTANT]
> The companion utility libraries are not available on public package managers
> (such as Maven). Follow the instructions below to clone and install the
> library.

1.  Clone the repository:
    ```shell
    git clone https://github.com/googleads/data-manager-java.git
    ```
2.  Determine the latest version of the library (`{version}`) in
    `data-manager-util/build.gradle` (e.g., `0.1.0`).
3.  Navigate to the `data-manager-java` directory.
4.  Build and publish the utility library to your local Maven repository:
    ```shell
    ./gradlew data-manager-util:install
    ```
5.  Declare a dependency on the utility library in your project. Replace
    `{version}` with the value found in step 2.
    *   **Gradle**:
        ```groovy
        implementation 'com.google.api-ads:data-manager-util:{version}'
        ```
    *   **Maven**:
        ```xml
        <dependency>
          <groupId>com.google.api-ads</groupId>
          <artifactId>data-manager-util</artifactId>
          <version>{version}</version>
        </dependency>
        ```
