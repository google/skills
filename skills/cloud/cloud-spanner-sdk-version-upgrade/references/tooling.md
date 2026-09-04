# Migration and Upgrade Tooling

Using the right tools can automate or simplify the process of upgrading dependencies and identifying breaking changes.

## Dependency Management Tools

### Node.js / JavaScript
- **`npm-check-updates` (ncu):** A CLI tool that upgrades your `package.json` dependencies to the latest versions, ignoring specified versions.
  `ncu -u`
- **`npm ls <package>`:** Helps identify why a specific version of a package is installed and what relies on it.

### Python
- **`pip-upgrader`:** An interactive tool to upgrade packages in `requirements.txt`.
- **`pipdeptree`:** Displays the installed Python packages in form of a dependency tree.

### Java
- **Maven Versions Plugin:** `mvn versions:display-dependency-updates` shows which dependencies have newer versions available.
- **Gradle Versions Plugin:** A similar tool for Gradle projects to discover dependency updates.

## Automated Refactoring Tools

For very large migrations, some ecosystems provide automated refactoring tools that can rewrite your code to use the new SDK APIs.

- **OpenRewrite (Java):** OpenRewrite can run "recipes" that automatically refactor Java code. Some SDK providers offer official OpenRewrite recipes for major version migrations (e.g., upgrading Spring Boot or AWS SDKs).
- **jscodeshift (JavaScript/TypeScript):** A toolkit for running "codemods" that transform ASTs. Often used by React or other UI frameworks, but sometimes provided by library authors for major upgrades.
- **Goof (Go):** Standard tools like `gofmt` and `go fix` can sometimes help with standard library upgrades.

## Continuous Update Bots
Consider enabling tools like **Dependabot** (GitHub) or **Renovate** to automate dependency updates. They create pull requests automatically when new versions are released, allowing you to run your CI pipeline against the new version immediately.
