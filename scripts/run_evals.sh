#!/bin/bash
# Validate schematizer output in a target repo.
# Usage: ./scripts/run_evals.sh <path-to-output-repo> [mode]
# Modes: audit, discover, combined, auto (default)
#
# Examples:
#   ./scripts/run_evals.sh /path/to/atlas-banking-platform audit
#   ./scripts/run_evals.sh ./test-repo auto

set -e

REPO_ROOT="${1:-.}"
MODE="${2:-auto}"
STATUS=0

echo "=== Schematizer Eval Runner ==="
echo "Repo: $REPO_ROOT"
echo "Mode: $MODE"
echo ""

# ─── Skill File Checks ───

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "=== Skill File Checks ==="

check_skill_file() {
    if [ -f "$SKILL_DIR/$1" ]; then
        echo "  OK  Skill file exists: $1"
    else
        echo "  WARN  Skill file missing: $1"
    fi
}

check_skill_file "skill.md"
check_skill_file "skill-scan.md"
check_skill_file "skill-audit-generate.md"
check_skill_file "skill-discover.md"
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
            echo "  OK  Found: $2"
        else
            echo "  FAIL  Missing: $2"
            STATUS=1
        fi
    }

    check_content "Category" "Category breakdown"
    check_content "Rollout|rollout" "Rollout ordering"
    check_content "Consumer Impact" "Consumer Impact Notes"
    check_content "HeaderSchemaIdSerializer" "HeaderSchemaIdSerializer guidance"
    warn_content() {
        if grep -Eqi "$1" "$REPORT"; then
            echo "  OK  Found: $2"
        else
            echo "  WARN  Missing: $2"
        fi
    }
    warn_content "CP 8\.0" "Java version CP 8.0+"
    warn_content "v2\.10\.1" "Python/Go/.NET version v2.10.1+"
    warn_content "v1\.3\.2" "Node version v1.3.2+"
    check_content "PII" "PII tagging"
    check_content "confluent_tag|confluent:tags" "Confluent tag resources or PII tags"

    # C-App / C-Connector terminology check
    if grep -Eqi "connector|debezium|Debezium" "$REPORT"; then
        echo ""
        echo "  === C-App / C-Connector Terminology Checks ==="
        if grep -Eq "C-App" "$REPORT"; then
            echo "  OK  Report uses C-App terminology"
        else
            echo "  FAIL  Report mentions connectors but does not use C-App terminology"
            STATUS=1
        fi
        if grep -Eq "C-Connector" "$REPORT"; then
            echo "  OK  Report uses C-Connector terminology"
        else
            echo "  FAIL  Report mentions connectors but does not use C-Connector terminology"
            STATUS=1
        fi
    fi

    # Category E specific checks
    if grep -Eqi "Category E|Custom serializer" "$REPORT"; then
        echo ""
        echo "  === Category E Checks ==="
        if grep -Eqi "replace.*custom|replace.*serializer" "$REPORT"; then
            echo "  OK  Category E: recommends replacing custom serializer"
        else
            echo "  FAIL  Category E: should recommend replacing custom serializer"
            STATUS=1
        fi
        if grep -Eqi "consumers first" "$REPORT"; then
            echo "  OK  Category E: consumers first rollout"
        else
            echo "  FAIL  Category E: should have consumers first rollout"
            STATUS=1
        fi
        if grep -Eqi "keep custom serializer" "$REPORT"; then
            echo "  FAIL  Category E: should NOT say 'keep custom serializer'"
            STATUS=1
        else
            echo "  OK  Category E: does not say 'keep custom serializer'"
        fi
    fi

    # Category C specific checks
    if grep -Eqi "Category C|auto.register" "$REPORT"; then
        echo ""
        echo "  === Category C Checks ==="
        FLAGGED_TF="$REPO_ROOT/terraform/flagged-auto-register.tf"
        if [ -f "$FLAGGED_TF" ]; then
            echo "  OK  Category C: flagged-auto-register.tf exists"
            if grep -q "^#.*confluent_schema" "$FLAGGED_TF"; then
                echo "  OK  Category C: resources are commented out"
            else
                echo "  FAIL  Category C: resources should be commented out"
                STATUS=1
            fi
        else
            echo "  FAIL  Category C: flagged-auto-register.tf not found"
            STATUS=1
        fi
    fi
fi

# ─── Contract Checks ───

CONTRACTS_DIR="$REPO_ROOT/contracts"
if [ -d "$CONTRACTS_DIR" ]; then
    echo ""
    echo "=== Contract File Checks ==="

    # Check contract files exist
    CONTRACT_COUNT=0
    for f in "$CONTRACTS_DIR"/*.yaml "$CONTRACTS_DIR"/*.yml "$CONTRACTS_DIR"/*.json; do
        if [ -f "$f" ]; then
            CONTRACT_COUNT=$((CONTRACT_COUNT + 1))
        fi
    done
    if [ "$CONTRACT_COUNT" -gt 0 ]; then
        echo "  OK  Found $CONTRACT_COUNT contract file(s) in contracts/"
    else
        echo "  FAIL  contracts/ directory exists but contains no contract files"
        STATUS=1
    fi

    # Schema purity check — schemas must NOT contain confluent:tags or confluent.field_meta
    echo ""
    echo "  === Schema Purity Checks ==="
    SCHEMAS_DIR="$REPO_ROOT/schemas"
    if [ -d "$SCHEMAS_DIR" ]; then
        IMPURE_FILES=""
        for schema_file in "$SCHEMAS_DIR"/*.avsc "$SCHEMAS_DIR"/*.json "$SCHEMAS_DIR"/*.proto "$SCHEMAS_DIR"/**/*.avsc "$SCHEMAS_DIR"/**/*.json "$SCHEMAS_DIR"/**/*.proto; do
            if [ -f "$schema_file" ]; then
                if grep -Eq "confluent:tags|confluent\.field_meta" "$schema_file" 2>/dev/null; then
                    IMPURE_FILES="$IMPURE_FILES $schema_file"
                fi
            fi
        done
        if [ -n "$IMPURE_FILES" ]; then
            echo "  FAIL  Schema files contain confluent:tags or confluent.field_meta (must be in contracts, not schemas):"
            for f in $IMPURE_FILES; do
                echo "        - $f"
            done
            STATUS=1
        else
            echo "  OK  Schema files are pure (no confluent:tags or confluent.field_meta)"
        fi
    else
        echo "  WARN  No schemas/ directory found — skipping purity check"
    fi

    # Check contracts reference valid tags
    echo ""
    echo "  === Contract Tag Reference Checks ==="
    CONTRACTS_WITH_TAGS=0
    for f in "$CONTRACTS_DIR"/*.yaml "$CONTRACTS_DIR"/*.yml "$CONTRACTS_DIR"/*.json; do
        if [ -f "$f" ]; then
            if grep -Eq "tag|Tag|PII|SENSITIVE|PUBLIC|PRIVATE" "$f" 2>/dev/null; then
                CONTRACTS_WITH_TAGS=$((CONTRACTS_WITH_TAGS + 1))
            fi
        fi
    done
    if [ "$CONTRACTS_WITH_TAGS" -gt 0 ]; then
        echo "  OK  $CONTRACTS_WITH_TAGS contract file(s) reference tags"
    else
        echo "  WARN  No contract files reference tags — expected at least one with PII/sensitivity tags"
    fi

    # Check contracts.tf exists when contracts/ is present
    echo ""
    echo "  === Contracts Terraform Check ==="
    CONTRACTS_TF="$REPO_ROOT/terraform/contracts.tf"
    if [ -f "$CONTRACTS_TF" ]; then
        echo "  OK  terraform/contracts.tf exists"
        if grep -Eq "confluent_tag_binding" "$CONTRACTS_TF" 2>/dev/null; then
            echo "  OK  contracts.tf contains confluent_tag_binding resources"
        else
            echo "  FAIL  contracts.tf missing confluent_tag_binding resources"
            STATUS=1
        fi
    else
        echo "  FAIL  contracts/ directory exists but terraform/contracts.tf not found"
        STATUS=1
    fi
else
    echo ""
    echo "=== Contract File Checks ==="
    echo "  WARN  No contracts/ directory found — skipping contract checks (legacy output structure)"

    # Still run schema purity check even without contracts dir
    SCHEMAS_DIR="$REPO_ROOT/schemas"
    if [ -d "$SCHEMAS_DIR" ]; then
        echo ""
        echo "  === Schema Purity Checks ==="
        IMPURE_FILES=""
        for schema_file in "$SCHEMAS_DIR"/*.avsc "$SCHEMAS_DIR"/*.json "$SCHEMAS_DIR"/*.proto "$SCHEMAS_DIR"/**/*.avsc "$SCHEMAS_DIR"/**/*.json "$SCHEMAS_DIR"/**/*.proto; do
            if [ -f "$schema_file" ]; then
                if grep -Eq "confluent:tags|confluent\.field_meta" "$schema_file" 2>/dev/null; then
                    IMPURE_FILES="$IMPURE_FILES $schema_file"
                fi
            fi
        done
        if [ -n "$IMPURE_FILES" ]; then
            echo "  FAIL  Schema files contain confluent:tags or confluent.field_meta:"
            for f in $IMPURE_FILES; do
                echo "        - $f"
            done
            STATUS=1
        else
            echo "  OK  Schema files are pure (no confluent:tags or confluent.field_meta)"
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
            echo "  OK  Found: $2"
        else
            echo "  FAIL  Missing: $2"
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
            echo "  OK  Candidates have pending_review status"
        else
            echo "  FAIL  Missing pending_review status (nothing should be auto-approved)"
            STATUS=1
        fi
        if grep -q "confidence" "$RECS"; then
            echo "  OK  Confidence levels assigned"
        else
            echo "  FAIL  Missing confidence levels"
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
            echo "  FAIL  Patches use raw serialization (should use Confluent serializer):"
            echo "     $BAD_PATCHES"
            STATUS=1
        else
            echo "  OK  No raw serialization in patches"
        fi
    fi
fi

# ─── Combined Mode Checks ───

SUMMARY="$REPO_ROOT/executive-summary.md"
if [ -f "$SUMMARY" ]; then
    echo ""
    echo "=== Combined Mode Checks ==="
    if grep -Eqi "Key Findings" "$SUMMARY"; then
        echo "  OK  Executive summary has Key Findings"
    else
        echo "  FAIL  Executive summary missing Key Findings"
        STATUS=1
    fi
    if grep -Eqi "Recommended Action Plan" "$SUMMARY"; then
        echo "  OK  Executive summary has Action Plan"
    else
        echo "  FAIL  Executive summary missing Action Plan"
        STATUS=1
    fi
fi

echo ""
if [ $STATUS -eq 0 ]; then
    echo "All eval checks passed (OK)"
else
    echo "Some eval checks failed (FAIL)"
fi
exit $STATUS
