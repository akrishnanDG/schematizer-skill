#!/bin/bash
# Run validation against schematizer output in a test repo.
# Usage: ./scripts/run_evals.sh <path-to-test-repo>

set -e

REPO_ROOT="${1:-.}"

echo "=== Schematizer Eval Runner ==="
echo "Repo: $REPO_ROOT"
echo ""

# Run the validation script
python3 "$(dirname "$0")/validate_output.py" "$REPO_ROOT"
STATUS=$?

echo ""

# Check report for required content
REPORT="$REPO_ROOT/schema-report.md"
if [ -f "$REPORT" ]; then
    echo "=== Report Content Checks ==="

    check_content() {
        if grep -qi "$1" "$REPORT"; then
            echo "  ✅ Found: $2"
        else
            echo "  ❌ Missing: $2"
            STATUS=1
        fi
    }

    check_content "Category" "Category breakdown"
    check_content "Rollout" "Rollout ordering"
    check_content "Consumer Impact" "Consumer Impact Notes"
    check_content "HeaderSchemaIdSerializer" "HeaderSchemaIdSerializer guidance"
    check_content "8\.1\.1\|8.1.1" "Java version 8.1.1+"
    check_content "2\.13\.0\|2.13.0" "Python/Go/.NET version 2.13.0+"
    check_content "1\.8\.0\|1.8.0" "Node version 1.8.0+"
    check_content "PII" "PII tagging"

    # Category E specific
    if grep -qi "Category E\|Custom serializer" "$REPORT"; then
        echo ""
        echo "  === Category E Checks ==="
        if grep -qi "replace.*custom\|replace.*serializer" "$REPORT"; then
            echo "  ✅ Category E: recommends replacing custom serializer"
        else
            echo "  ❌ Category E: should recommend replacing custom serializer"
            STATUS=1
        fi
        if grep -qi "consumers first" "$REPORT"; then
            echo "  ✅ Category E: consumers first rollout"
        else
            echo "  ❌ Category E: should have consumers first rollout"
            STATUS=1
        fi
        if grep -qi "keep custom serializer" "$REPORT"; then
            echo "  ❌ Category E: should NOT say 'keep custom serializer'"
            STATUS=1
        else
            echo "  ✅ Category E: does not say 'keep custom serializer'"
        fi
    fi
fi

echo ""
if [ $STATUS -eq 0 ]; then
    echo "All eval checks passed ✅"
else
    echo "Some eval checks failed ❌"
fi
exit $STATUS
