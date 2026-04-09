#!/usr/bin/env python3
"""Validate schematizer skill output: Audit, Discover, and Combined modes.

Usage:
    python3 validate_output.py <repo-root> [mode]

Modes: audit, discover, combined, auto (default — auto-detects from output files)
"""

import json
import os
import sys
from pathlib import Path


def validate_schemas(repo_root: str) -> list[str]:
    """Check that extracted schema files are valid."""
    errors = []
    schemas_dir = Path(repo_root) / "schemas"
    if not schemas_dir.exists():
        errors.append("schemas/ directory not found")
        return errors

    for ext, fmt in [(".json", "JSON Schema"), (".avsc", "Avro"), (".proto", "Protobuf")]:
        for f in schemas_dir.rglob(f"*{ext}"):
            if ext in (".json", ".avsc"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                    if ext == ".json":
                        if "$schema" not in data and "type" not in data:
                            errors.append(f"{f}: missing '$schema' or 'type' field")
                    if ext == ".avsc":
                        if "type" not in data:
                            errors.append(f"{f}: missing 'type' field for Avro schema")
                        if data.get("type") == "record":
                            for field in data.get("fields", []):
                                if "default" not in field:
                                    errors.append(
                                        f"{f}: field '{field.get('name')}' missing 'default' (evolution risk)"
                                    )
                except json.JSONDecodeError as e:
                    errors.append(f"{f}: invalid JSON — {e}")
            elif ext == ".proto":
                content = f.read_text()
                if "syntax" not in content:
                    errors.append(f"{f}: missing 'syntax' declaration")
    return errors


def validate_terraform(repo_root: str) -> list[str]:
    """Check that Terraform files exist and have expected resources."""
    errors = []
    tf_dir = Path(repo_root) / "terraform"
    if not tf_dir.exists():
        errors.append("terraform/ directory not found")
        return errors

    expected_files = ["providers.tf", "variables.tf", "schemas.tf"]
    for fname in expected_files:
        if not (tf_dir / fname).exists():
            errors.append(f"terraform/{fname} not found")

    schemas_tf = tf_dir / "schemas.tf"
    if schemas_tf.exists():
        content = schemas_tf.read_text()
        if "confluent_schema" not in content:
            errors.append("terraform/schemas.tf: no confluent_schema resources found")
        if "schema_registry_cluster" not in content:
            errors.append("terraform/schemas.tf: missing schema_registry_cluster block (provider v2.x)")

    variables_tf = tf_dir / "variables.tf"
    if variables_tf.exists():
        content = variables_tf.read_text()
        if "sensitive" not in content:
            errors.append("terraform/variables.tf: credentials should be marked sensitive")

    # Check tags.tf if schemas use PII tags
    if schemas_tf and schemas_tf.exists() and "confluent:tags" in schemas_tf.read_text():
        tags_tf = tf_dir / "tags.tf"
        if not tags_tf.exists():
            errors.append("terraform/tags.tf: not found but schemas use confluent:tags")
        elif "confluent_tag" not in tags_tf.read_text():
            errors.append("terraform/tags.tf: missing confluent_tag resources")

    # Check outputs.tf and import.sh
    if not (tf_dir / "outputs.tf").exists():
        errors.append("terraform/outputs.tf not found")
    if not (tf_dir / "import.sh").exists():
        errors.append("terraform/import.sh not found")

    # Check CI/CD
    ci_file = tf_dir / "ci" / "schema-lint.yml"
    if not ci_file.exists():
        errors.append("terraform/ci/schema-lint.yml not found (Phase 8)")

    return errors


def validate_report(repo_root: str) -> list[str]:
    """Check that the Audit report has required sections."""
    errors = []
    report = Path(repo_root) / "schema-report.md"
    if not report.exists():
        errors.append("schema-report.md not found")
        return errors

    content = report.read_text()
    required = [
        ("Executive Summary", "executive summary"),
        ("Applications Discovered", "applications table"),
        ("Schemas Extracted", "schemas table"),
        ("Next Steps", "next steps checklist"),
    ]
    for section, desc in required:
        if section not in content:
            errors.append(f"schema-report.md: missing '{section}' section ({desc})")

    if "Category" not in content:
        errors.append("schema-report.md: missing category breakdown")
    if "rollout" not in content.lower():
        errors.append("schema-report.md: missing rollout ordering guidance")
    if "PII" not in content:
        errors.append("schema-report.md: missing PII section")
    if "HeaderSchemaIdSerializer" not in content:
        errors.append("schema-report.md: missing HeaderSchemaIdSerializer guidance")

    # Check version numbers match verified sources
    for version in ["CP 8.0", "v2.10.1", "v1.3.2"]:
        if version not in content:
            errors.append(f"schema-report.md: missing version reference '{version}'")

    return errors


def validate_discover(repo_root: str) -> list[str]:
    """Check that Discover mode outputs are valid."""
    errors = []
    discover_dir = Path(repo_root) / "discover"
    if not discover_dir.exists():
        errors.append("discover/ directory not found")
        return errors

    # kafka_recommendations.yaml
    recs = discover_dir / "kafka_recommendations.yaml"
    if not recs.exists():
        errors.append("discover/kafka_recommendations.yaml not found")
    else:
        content = recs.read_text()
        if "pending_review" not in content:
            errors.append("kafka_recommendations.yaml: missing 'pending_review' status")
        if "confidence" not in content:
            errors.append("kafka_recommendations.yaml: missing confidence levels")
        for field in ["event_id", "event_type", "event_timestamp"]:
            if field not in content:
                errors.append(f"kafka_recommendations.yaml: missing envelope field '{field}'")

    # kafka_schemas.yaml
    if not (discover_dir / "kafka_schemas.yaml").exists():
        errors.append("discover/kafka_schemas.yaml not found")

    # patches
    patches_dir = discover_dir / "patches"
    if not patches_dir.exists():
        errors.append("discover/patches/ directory not found")
    else:
        patches = list(patches_dir.glob("*.patch"))
        if not patches:
            errors.append("discover/patches/: no .patch files found")
        for patch in patches:
            content = patch.read_text()
            if "---" not in content or "+++" not in content:
                errors.append(f"{patch.name}: invalid unified diff (missing --- or +++)")

    return errors


def validate_discover_report(repo_root: str) -> list[str]:
    """Check that the Discover report has required sections."""
    errors = []
    report = Path(repo_root) / "discover-report.md"
    if not report.exists():
        errors.append("discover-report.md not found")
        return errors

    content = report.read_text()
    for section in ["Executive Summary", "Event Candidates", "Next Steps"]:
        if section not in content:
            errors.append(f"discover-report.md: missing '{section}' section")
    if "PII" not in content and "pii" not in content.lower():
        errors.append("discover-report.md: missing PII section")

    return errors


def validate_combined(repo_root: str) -> list[str]:
    """Check that Combined mode executive summary exists."""
    errors = []
    summary = Path(repo_root) / "executive-summary.md"
    if not summary.exists():
        errors.append("executive-summary.md not found")
        return errors

    content = summary.read_text()
    for section in ["Key Findings", "Recommended Action Plan"]:
        if section not in content:
            errors.append(f"executive-summary.md: missing '{section}' section")

    return errors


def main():
    repo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    mode = sys.argv[2] if len(sys.argv) > 2 else "auto"

    print(f"Validating schematizer output in: {os.path.abspath(repo_root)}")
    print(f"Mode: {mode}\n")

    # Auto-detect mode
    if mode == "auto":
        has_report = (Path(repo_root) / "schema-report.md").exists()
        has_discover = (Path(repo_root) / "discover").exists()
        has_summary = (Path(repo_root) / "executive-summary.md").exists()
        if has_summary or (has_report and has_discover):
            mode = "combined"
        elif has_discover:
            mode = "discover"
        elif has_report:
            mode = "audit"
        else:
            print("No output files detected. Run the schematizer skill first.")
            sys.exit(1)
        print(f"Auto-detected mode: {mode}\n")

    all_errors = []

    if mode in ("audit", "combined"):
        for name, validator in [
            ("Schemas", validate_schemas),
            ("Terraform", validate_terraform),
            ("Audit Report", validate_report),
        ]:
            errors = validator(repo_root)
            if errors:
                print(f"  {name}:")
                for e in errors:
                    print(f"   - {e}")
                all_errors.extend(errors)
            else:
                print(f"  {name}: OK")

    if mode in ("discover", "combined"):
        for name, validator in [
            ("Discover Outputs", validate_discover),
            ("Discover Report", validate_discover_report),
        ]:
            errors = validator(repo_root)
            if errors:
                print(f"  {name}:")
                for e in errors:
                    print(f"   - {e}")
                all_errors.extend(errors)
            else:
                print(f"  {name}: OK")

    if mode == "combined":
        errors = validate_combined(repo_root)
        if errors:
            print(f"  Combined Summary:")
            for e in errors:
                print(f"   - {e}")
            all_errors.extend(errors)
        else:
            print(f"  Combined Summary: OK")

    print()
    if all_errors:
        print(f"Found {len(all_errors)} issue(s)")
        sys.exit(1)
    else:
        print("All validations passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
