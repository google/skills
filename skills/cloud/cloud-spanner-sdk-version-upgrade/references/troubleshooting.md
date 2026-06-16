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
