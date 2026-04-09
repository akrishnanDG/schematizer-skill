#!/bin/bash
# Validate schematizer output in a target repo.
# Usage: ./scripts/run_evals.sh <path-to-output-repo> [mode]
# Modes: audit, discover, combined, auto (default)

set -e

REPO_ROOT="${1:-.}"
MODE="${2:-auto}"
STATUS=0

echo "=== Schematizer Eval Runner ==="
echo "Repo: $REPO_ROOT"
echo "Mode: $MODE"
echo ""

# Run the validation script
python3 "$(dirname "$0")/validate_output.py" "$REPO_ROOT" "$MODE" || STATUS=$?

echo ""

# ─── Audit Report Checks ───

REPORT="$REPO_ROOT/schema-report.md"
if [ -f "$REPORT" ]; then
    echo "=== Audit Report Content Checks ==="

    check_content() {
        if grep -Eqi "$1" "$REPORT"; then
            echo "  ✅ Found: $2"
        else
            echo "  ❌ Missing: $2"
            STATUS=1
        fi
    }

    check_content "Category" "Category breakdown"
    check_content "Rollout|rollout" "Rollout ordering"
    check_content "Consumer Impact" "Consumer Impact Notes"
    check_content "HeaderSchemaIdSerializer" "HeaderSchemaIdSerializer guidance"
    check_content "CP 8\.0" "Java version CP 8.0+"
    check_content "v2\.10\.1" "Python/Go/.NET version v2.10.1+"
    check_content "v1\.3\.2" "Node version v1.3.2+"
    check_content "PII" "PII tagging"
    check_content "confluent_tag|confluent:tags" "Confluent tag resources or PII tags"

    # Category E specific checks
    if grep -Eqi "Category E|Custom serializer" "$REPORT"; then
        echo ""
        echo "  === Category E Checks ==="
        if grep -Eqi "replace.*custom|replace.*serializer" "$REPORT"; then
            echo "  ✅ Category E: recommends replacing custom serializer"
        else
            echo "  ❌ Category E: should recommend replacing custom serializer"
            STATUS=1
        fi
        if grep -Eqi "consumers first" "$REPORT"; then
            echo "  ✅ Category E: consumers first rollout"
        else
            echo "  ❌ Category E: should have consumers first rollout"
            STATUS=1
        fi
        if grep -Eqi "keep custom serializer" "$REPORT"; then
            echo "  ❌ Category E: should NOT say 'keep custom serializer'"
            STATUS=1
        else
            echo "  ✅ Category E: does not say 'keep custom serializer'"
        fi
    fi

    # Category C specific checks
    if grep -Eqi "Category C|auto.register" "$REPORT"; then
        echo ""
        echo "  === Category C Checks ==="
        FLAGGED_TF="$REPO_ROOT/terraform/flagged-auto-register.tf"
        if [ -f "$FLAGGED_TF" ]; then
            echo "  ✅ Category C: flagged-auto-register.tf exists"
            if grep -q "^#.*confluent_schema" "$FLAGGED_TF"; then
                echo "  ✅ Category C: resources are commented out"
            else
                echo "  ❌ Category C: resources should be commented out"
                STATUS=1
            fi
        else
            echo "  ❌ Category C: flagged-auto-register.tf not found"
            STATUS=1
        fi
    fi
fi

# ─── Discover Report Checks ───

DISCOVER_REPORT="$REPO_ROOT/discover-report.md"
if [ -f "$DISCOVER_REPORT" ]; then
    echo ""
    echo "=== Discover Report Content Checks ==="

    check_discover() {
        if grep -Eqi "$1" "$DISCOVER_REPORT"; then
            echo "  ✅ Found: $2"
        else
            echo "  ❌ Missing: $2"
            STATUS=1
        fi
    }

    check_discover "Executive Summary" "Executive Summary section"
    check_discover "Event Candidates|Candidate" "Event Candidates section"
    check_discover "PII|pii" "PII detection results"
    check_discover "Next Steps" "Next Steps section"

    # Check recommendations YAML
    RECS="$REPO_ROOT/discover/kafka_recommendations.yaml"
    if [ -f "$RECS" ]; then
        echo ""
        echo "  === Recommendations YAML Checks ==="
        if grep -q "pending_review" "$RECS"; then
            echo "  ✅ Candidates have pending_review status"
        else
            echo "  ❌ Missing pending_review status (nothing should be auto-approved)"
            STATUS=1
        fi
        if grep -q "confidence" "$RECS"; then
            echo "  ✅ Confidence levels assigned"
        else
            echo "  ❌ Missing confidence levels"
            STATUS=1
        fi
    fi

    # Check patches don't use raw serialization
    PATCHES_DIR="$REPO_ROOT/discover/patches"
    if [ -d "$PATCHES_DIR" ]; then
        echo ""
        echo "  === Patch Quality Checks ==="
        BAD_PATCHES=$(grep -Erl "json\.dumps|JSON\.stringify|objectMapper\.writeValueAsString" "$PATCHES_DIR" 2>/dev/null || true)
        if [ -n "$BAD_PATCHES" ]; then
            echo "  ❌ Patches use raw serialization (should use Confluent serializer):"
            echo "     $BAD_PATCHES"
            STATUS=1
        else
            echo "  ✅ No raw serialization in patches"
        fi
    fi
fi

# ─── Combined Mode Checks ───

SUMMARY="$REPO_ROOT/executive-summary.md"
if [ -f "$SUMMARY" ]; then
    echo ""
    echo "=== Combined Mode Checks ==="
    if grep -Eqi "Key Findings" "$SUMMARY"; then
        echo "  ✅ Executive summary has Key Findings"
    else
        echo "  ❌ Executive summary missing Key Findings"
        STATUS=1
    fi
    if grep -Eqi "Recommended Action Plan" "$SUMMARY"; then
        echo "  ✅ Executive summary has Action Plan"
    else
        echo "  ❌ Executive summary missing Action Plan"
        STATUS=1
    fi
fi

echo ""
if [ $STATUS -eq 0 ]; then
    echo "All eval checks passed ✅"
else
    echo "Some eval checks failed ❌"
fi
exit $STATUS
