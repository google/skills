#!/bin/bash
# OpenRewrite Runner Script
# This script executes OpenRewrite recipes on Maven projects to automate code refactoring.

set -euo pipefail

TARGET_DIR="${1:-.}"
RECIPE="${2:-jakarta}" # Options: jakarta, java17, spring3, quarkus

if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory $TARGET_DIR does not exist." >&2
    exit 1
fi

# Get the directory of this script to find helper scripts
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TEMP_POM_CREATED=false

# Cleanup function to remove temp pom if created
cleanup() {
    if [ "$TEMP_POM_CREATED" = true ]; then
        echo "Cleaning up temporary pom.xml..."
        rm -f "$TARGET_DIR/pom.xml"
    fi
}
trap cleanup EXIT

# Check if pom.xml exists in target directory, if not, generate a temporary one
if [ ! -f "$TARGET_DIR/pom.xml" ]; then
    echo "No pom.xml found. Attempting to generate a temporary pom.xml for refactoring..."
    python3 "$SCRIPT_DIR/generate_temp_pom.py" "$TARGET_DIR"
    TEMP_POM_CREATED=true
fi

echo "===================================================="
echo " Running OpenRewrite Refactoring"
echo " Target Directory: $TARGET_DIR"
echo " Recipe Selected:  $RECIPE"
echo "===================================================="

# Determine active recipes and dependencies
case "$RECIPE" in
    jakarta)
        ACTIVE_RECIPES="org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta"
        # We need the rewrite-migrate-java artifact for Jakarta migration recipes
        RECIPE_COORDS="org.openrewrite.recipe:rewrite-migrate-java:2.9.0"
        ;;
    java17)
        ACTIVE_RECIPES="org.openrewrite.java.migrate.UpgradeToJava17"
        RECIPE_COORDS="org.openrewrite.recipe:rewrite-migrate-java:2.9.0"
        ;;
    spring3)
        ACTIVE_RECIPES="org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0"
        RECIPE_COORDS="org.openrewrite.recipe:rewrite-spring:5.5.0"
        ;;
    quarkus)
        ACTIVE_RECIPES="org.openrewrite.java.quarkus.quarkus3.Quarkus3Migration"
        RECIPE_COORDS="org.openrewrite.recipe:rewrite-quarkus:2.1.0"
        ;;
    *)
        echo "Error: Unknown recipe '$RECIPE'. Supported: jakarta, java17, spring3, quarkus" >&2
        exit 1
        ;;
esac

# Run Maven command
# Note: This will download the plugin and recipes if not already in local m2 cache.
(
    cd "$TARGET_DIR"
    mvn org.openrewrite.maven:rewrite-maven-plugin:5.15.0:run \
      -DactiveRecipes="$ACTIVE_RECIPES" \
      -Drewrite.recipeArtifactCoordinates="$RECIPE_COORDS" \
      -Drewrite.exportDatatable=true
)

echo "===================================================="
echo " Refactoring Run Complete."
echo " Review changes using git diff."
echo "===================================================="
