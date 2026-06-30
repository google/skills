# Troubleshooting SDK Upgrades

When an SDK upgrade fails or causes issues, use these strategies to diagnose and resolve the problem.

## Common Issues & Solutions

### 1. "Method / Class Not Found" (Compilation Error)
**Symptom:** The compiler or runtime complains that a specific function, class, or module no longer exists.
**Diagnosis:** This is a classic breaking change. The method was likely deprecated in a previous version and removed in the new major version.
**Resolution:** 
- Check the official migration guide or changelog.
- Look for the replacement method. Often, configuration objects replace long parameter lists, or synchronous methods are replaced by asynchronous ones.

### 2. Dependency Conflicts / Resolution Errors
**Symptom:** Package manager (`npm`, `pip`, `maven`) fails to install, citing conflicting versions.
**Diagnosis:** The new SDK requires a newer version of a shared dependency (like `requests` in Python or `jackson` in Java) that conflicts with another library you are using.
**Resolution:**
- Use dependency tree commands (`npm ls`, `pipdeptree`, `mvn dependency:tree`) to find the conflict.
- You may need to upgrade the conflicting library as well, or use dependency overrides/resolutions if absolutely necessary.

### 3. Silent Failures / Unexpected Behavior Change
**Symptom:** The code compiles and runs, but the API returns different results, or authentication fails silently.
**Diagnosis:** The new SDK might have changed default behaviors (e.g., default timeouts, retry logic, or data formats like returning JSON instead of raw strings).
**Resolution:**
- Enable debug logging for the SDK if available.
- Inspect network traffic (using proxy tools or network inspectors) to see exactly what the old SDK sent vs. what the new SDK is sending.
- Review the "Behavioral Changes" section of the release notes.

### 4. Authentication Errors
**Symptom:** "Unauthorized" or "Forbidden" errors after upgrading.
**Diagnosis:** The authentication mechanism or the way credentials are provided may have changed. For example, moving from API keys to OAuth, or changing how the client is initialized.
**Resolution:** Check the initialization block of the client. Ensure the credentials object matches the new expected schema.

## Language-Specific Troubleshooting (e.g., Cloud Spanner)

When upgrading complex multi-language SDKs like Google Cloud Spanner, watch out for these notorious language-specific pitfalls that often evade standard changelogs:

### Java
**Symptom:** `NoSuchMethodError` crashes at runtime.
**Diagnosis:** The Spanner SDK heavily relies on Google's Guava and Protobuf libraries. Upgrades often bump the required Guava version, which breaks execution if your project's dependency tree (or a Spring Boot BOM) forces an older Guava version.
**Resolution:** Always inspect the dependency tree (`mvn dependency:tree` or `gradle dependencies`) for Guava or Protobuf transitive version conflicts and align them with the SDK's expectations.

### Node.js
**Symptom:** Spanner client fails to connect or throws gRPC option formatting errors.
**Diagnosis:** Spanner upgrades alter underlying `gax-nodejs` and `grpc` internals. This breaks applications that pass custom `grpc` connection options or SSL configurations to the Spanner constructor.
**Resolution:** Review the application's client initialization for custom `grpc` shapes. Also, strictly check `engines` in `package.json` since modern SDK upgrades drop support for older Node versions (e.g., Node 14/16).

### Go
**Symptom:** Obscure runtime dial errors or panics.
**Diagnosis:** The Go Spanner client is deeply coupled with `google.golang.org/grpc` and `google.golang.org/api`. Upgrading Spanner without aligning these transitive dependencies causes version mismatch panics at runtime.
**Resolution:** Always run `go mod tidy` after bumping the Spanner client. Explicitly verify the `grpc` version matrix to ensure transitive APIs are compatible.

### Python
**Symptom:** Runtime exceptions during parameterized `execute_sql` queries.
**Diagnosis:** Older versions of the Python Spanner client were lenient with parameterized types. Newer versions (backed by updated GAPIC generators) enforce strict type matching.
**Resolution:** Review all instances of `execute_sql()`. Ensure `param_types` are explicitly provided for all parameterized queries to avoid runtime type errors.
