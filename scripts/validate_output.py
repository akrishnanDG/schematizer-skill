#!/usr/bin/env python3
"""Validate schematizer skill output: schemas, Terraform, and report."""

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
                    if ext == ".json" and "$schema" not in data and "type" not in data:
                        errors.append(f"{f}: missing '$schema' or 'type' field")
                    if ext == ".avsc" and "type" not in data:
                        errors.append(f"{f}: missing 'type' field for Avro schema")
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

    variables_tf = tf_dir / "variables.tf"
    if variables_tf.exists():
        content = variables_tf.read_text()
        if "sensitive" not in content:
            errors.append("terraform/variables.tf: credentials should be marked sensitive")
    return errors


def validate_report(repo_root: str) -> list[str]:
    """Check that the report has required sections."""
    errors = []
    report = Path(repo_root) / "schema-report.md"
    if not report.exists():
        errors.append("schema-report.md not found")
        return errors

    content = report.read_text()
    required_sections = [
        "Executive Summary",
        "Applications Discovered",
        "Schemas Extracted",
        "Consumer Impact Notes",
        "Next Steps",
    ]
    for section in required_sections:
        if section not in content:
            errors.append(f"schema-report.md: missing '{section}' section")

    if "Rollout Order" not in content and "rollout" not in content.lower():
        errors.append("schema-report.md: missing rollout ordering guidance")
    return errors


def main():
    repo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    print(f"Validating schematizer output in: {os.path.abspath(repo_root)}\n")

    all_errors = []
    for name, validator in [
        ("Schemas", validate_schemas),
        ("Terraform", validate_terraform),
        ("Report", validate_report),
    ]:
        errors = validator(repo_root)
        if errors:
            print(f"❌ {name}:")
            for e in errors:
                print(f"   - {e}")
            all_errors.extend(errors)
        else:
            print(f"✅ {name}: OK")

    print()
    if all_errors:
        print(f"Found {len(all_errors)} issue(s)")
        sys.exit(1)
    else:
        print("All validations passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
