## Example config for project setup

### Python

Python has shifted toward a more unified configuration approach recently, but
you'll still see a mix of old and new.

*   pyproject.toml: The modern standard for defining build systems and project
    metadata.
*   requirements.txt: A simple list of dependencies for pip.
*   setup.py / setup.cfg: Legacy files for packaging and distribution.
*   environment.yml: Used specifically for Conda virtual environments.
*   tox.ini: Configuration for automated testing across different Python
    versions.

### Java

Java relies heavily on established build automation tools.

*   pom.xml: The core configuration file for Maven projects.
*   build.gradle: The build script for Gradle (Groovy DSL).
*   settings.gradle: Defines project structure and module names for Gradle.
*   MANIFEST.MF: Defines extension and package-related data for JAR files.

### Go (Golang)

Go keeps it minimal with a focus on reproducibility.

*   go.mod: Defines the module's path and its dependency requirements.
*   go.sum: Contains the expected cryptographic hashes of the content of
    specific module versions.

### Ruby

Ruby’s ecosystem is centered around "Gems."

*   Gemfile: Describes the gem dependencies required to run the Ruby code.
*   Gemfile.lock: Records the exact versions of gems that were installed.
*   .ruby-version: Specifies which version of the Ruby interpreter should be
    used.
*   Rakefile: Contains instructions for rake (Ruby's build program).

### Node.js

The JavaScript/TypeScript ecosystem is highly standardized.

*   package.json: Manifest file containing metadata, scripts, and dependencies.
*   package-lock.json (or yarn.lock / pnpm-lock.yaml): Ensures consistent
    installation across machines.
*   tsconfig.json: Configuration for TypeScript compiler settings.
*   .npmrc: Configuration file for how npm should behave.

### Rust

Rust uses a single, powerful tool called Cargo.

*   Cargo.toml: The manifest file where you declare dependencies and metadata.
*   Cargo.lock: Created automatically to ensure reproducible builds by locking
    dependency versions.

### Kotlin

Since Kotlin is often used in the JVM or Android ecosystem, it shares tools with
Java but uses its own "flavor."

*   build.gradle.kts: Gradle build script using the Kotlin DSL.
*   settings.gradle.kts: Project-wide settings using Kotlin DSL.

### PHP

Modern PHP development revolves around Composer.

*   composer.json: Defines dependencies, autoloading rules, and project
    metadata.
*   composer.lock: Locks the project to specific versions of dependencies.
*   php.ini: The main configuration file for the PHP interpreter itself.

### C / C++

These languages are more fragmented, often depending on the build system chosen.

*   Makefile: Used by the make build automation tool.
*   CMakeLists.txt: Configuration for CMake, the industry standard for
    cross-platform C/C++ builds.
*   conanfile.txt / conanfile.py: Used by the Conan package manager.
*   vcpkg.json: Configuration for the vcpkg dependency manager.

### Visual Studio (IDE Specific)

While the languages above use the files listed, the Visual Studio IDE adds its
own layer.

*   .sln: The Solution file; acts as a container for one or more projects.
*   .csproj / .vcxproj: Project files for C# and C++ respectively, containing
    build settings and file references.
*   .editorconfig: Defines coding styles (indentation, etc.) to be enforced by
    the editor.
*   App.config / Web.config: XML files for runtime configuration settings.
