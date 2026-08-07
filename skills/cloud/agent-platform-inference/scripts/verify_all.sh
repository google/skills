#!/bin/bash
set -e

# Verify against the ambient interpreter, which is the one the skill's scripts
# actually run under. A throwaway venv would verify an environment no real
# invocation ever uses, so it could pass while the real one is broken.
echo "Checking dependencies..."
python3 -c "import vertexai, google.genai, openai" \
  || pip install -q -r scripts/requirements.txt

echo "Running verification tests..."
FAILED=0

# Iterate directly over the files in the scripts directory
for script in scripts/*.py; do
  echo "Running $script..."
  if python3 "$script" > /dev/null 2>&1; then
    echo "  PASS: $script"
  else
    echo "  FAIL: $script"
    python3 "$script" # Run again to show output
    FAILED=1
  fi
done

if [[ $FAILED -eq 0 ]]; then
  echo "All scripts passed verification!"
  exit 0
else
  echo "Some scripts failed verification."
  exit 1
fi
