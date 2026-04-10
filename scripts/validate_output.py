#!/usr/bin/env python3
"""Validate schematizer skill output: Audit, Discover, Scan, and Combined modes.

Usage:
    python3 validate_output.py <repo-root> [mode]

Modes: audit, discover, scan, combined, auto (default — auto-detects from output files)
"""

import json
import os
import sys
from pathlib import Path

VALID_TAGS = {"PII", "PRIVATE", "SENSITIVE", "PHI", "PUBLIC"}


def validate_schemas(repo_root: str) -> list[str]:
    """Check that extracted schema files are valid and pure (no tags/metadata)."""
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
                    # Schema purity check — tags belong in contract files only
                    raw = f.read_text()
                    if "confluent:tags" in raw:
                        errors.append(f"{f}: contains 'confluent:tags' — schemas must be pure (use contract files for tags)")
                    if "confluent.field_meta" in raw:
                        errors.append(f"{f}: contains 'confluent.field_meta' — schemas must be pure (use contract files for tags)")
                except json.JSONDecodeError as e:
                    errors.append(f"{f}: invalid JSON — {e}")
            elif ext == ".proto":
                content = f.read_text()
                if "syntax" not in content:
                    errors.append(f"{f}: missing 'syntax' declaration")
                if "confluent:tags" in content:
                    errors.append(f"{f}: contains 'confluent:tags' — schemas must be pure (use contract files for tags)")
                if "confluent.field_meta" in content:
                    errors.append(f"{f}: contains 'confluent.field_meta' — schemas must be pure (use contract files for tags)")
    return errors


def validate_contracts(repo_root: str) -> list[str]:
    """Check that contract files are valid and have required fields."""
    errors = []
    contracts_dir = Path(repo_root) / "contracts"
    if not contracts_dir.exists():
        errors.append("contracts/ directory not found")
        return errors

    contract_files = list(contracts_dir.rglob("*.contract.json"))
    if not contract_files:
        errors.append("contracts/: no .contract.json files found")
        return errors

    for f in contract_files:
        try:
            with open(f) as fh:
                data = json.load(fh)
        except json.JSONDecodeError as e:
            errors.append(f"{f}: invalid JSON — {e}")
            continue

        # subject field
        if "subject" not in data:
            errors.append(f"{f}: missing 'subject' field")
        elif not isinstance(data["subject"], str):
            errors.append(f"{f}: 'subject' must be a string")

        # metadata.tags
        metadata = data.get("metadata", {})
        tags = metadata.get("tags") if isinstance(metadata, dict) else None
        if tags is None:
            errors.append(f"{f}: missing 'metadata.tags' field")
        elif not isinstance(tags, dict):
            errors.append(f"{f}: 'metadata.tags' must be a dict mapping field paths to tag lists")
        else:
            for field_path, tag_list in tags.items():
                if not field_path.startswith("*."):
                    errors.append(f"{f}: field path '{field_path}' must start with '*.' (e.g., '*.email')")
                if not isinstance(tag_list, list):
                    errors.append(f"{f}: tags for '{field_path}' must be a list")
                else:
                    for tag in tag_list:
                        if tag not in VALID_TAGS:
                            errors.append(f"{f}: invalid tag '{tag}' for '{field_path}' — must be one of {VALID_TAGS}")

        # ruleSet validation
        rule_set = data.get("ruleSet")
        if rule_set is not None:
            domain_rules = rule_set.get("domainRules")
            if domain_rules is not None and not isinstance(domain_rules, list):
                errors.append(f"{f}: 'ruleSet.domainRules' must be a list")
            if isinstance(domain_rules, list):
                for rule in domain_rules:
                    if not isinstance(rule, dict):
                        continue
                    rule_type = rule.get("type", "")
                    if rule_type == "ENCRYPT":
                        params = rule.get("params", {})
                        if "encrypt.kek.name" not in params:
                            errors.append(f"{f}: ENCRYPT rule missing 'encrypt.kek.name' in params")
                        if "encrypt.kms.type" in params:
                            errors.append(f"{f}: ENCRYPT rule should use 'encrypt.kek.name', not 'encrypt.kms.type'")

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
        # Schemas should NOT have tags — tags belong in contracts.tf
        if "confluent:tags" in content:
            errors.append("terraform/schemas.tf: contains 'confluent:tags' — tags belong in contracts.tf")
        # Schemas should NOT depend on tags — they are registered independently
        if "depends_on" in content and "tag" in content.lower():
            errors.append("terraform/schemas.tf: has depends_on referencing tags — schemas are registered independently")

    variables_tf = tf_dir / "variables.tf"
    if variables_tf.exists():
        content = variables_tf.read_text()
        if "sensitive" not in content:
            errors.append("terraform/variables.tf: credentials should be marked sensitive")

    # Check contracts.tf if contract files exist
    contracts_dir = Path(repo_root) / "contracts"
    has_contracts = contracts_dir.exists() and any(contracts_dir.rglob("*.contract.json"))
    if has_contracts:
        contracts_tf = tf_dir / "contracts.tf"
        if not contracts_tf.exists():
            errors.append("terraform/contracts.tf: not found but contract files exist")
        else:
            content = contracts_tf.read_text()
            if "confluent_tag_binding" not in content:
                errors.append("terraform/contracts.tf: missing confluent_tag_binding resources")

        tags_tf = tf_dir / "tags.tf"
        if not tags_tf.exists():
            errors.append("terraform/tags.tf: not found but contract files exist")
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

    # C-App vs C-Connector distinction check
    content_lower = content.lower()
    mentions_auto_register = "auto.register.schemas" in content
    mentions_connector = "debezium" in content_lower or "connector" in content_lower
    if mentions_auto_register and mentions_connector:
        has_c_app = "C-App" in content or "c-app" in content_lower
        has_c_connector = "C-Connector" in content or "c-connector" in content_lower
        if not (has_c_app and has_c_connector):
            errors.append(
                "schema-report.md: mentions auto.register.schemas and connectors but does not distinguish C-App from C-Connector"
            )

    return errors


def _find_discover_dir(repo_root: str) -> Path | None:
    """Find discover output directory — may be at root or under a service subdir."""
    root = Path(repo_root)
    # Check root-level discover/
    if (root / "discover").exists():
        return root / "discover"
    # Check {service}/discover/ pattern
    for child in root.iterdir():
        if child.is_dir() and (child / "discover").exists():
            return child / "discover"
    return None


def _find_discover_report(repo_root: str) -> Path | None:
    """Find discover-report.md — may be at root or under a service subdir."""
    root = Path(repo_root)
    if (root / "discover-report.md").exists():
        return root / "discover-report.md"
    for child in root.iterdir():
        if child.is_dir() and (child / "discover-report.md").exists():
            return child / "discover-report.md"
    return None


def validate_discover(repo_root: str) -> list[str]:
    """Check that Discover mode outputs are valid."""
    errors = []
    discover_dir = _find_discover_dir(repo_root)
    if discover_dir is None:
        errors.append("discover/ directory not found (checked root and service subdirs)")
        return errors

    # kafka_recommendations.yaml
    recs = discover_dir / "kafka_recommendations.yaml"
    if not recs.exists():
        errors.append(f"{discover_dir}/kafka_recommendations.yaml not found")
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
        errors.append(f"{discover_dir}/kafka_schemas.yaml not found")

    # patches
    patches_dir = discover_dir / "patches"
    if not patches_dir.exists():
        errors.append(f"{discover_dir}/patches/ directory not found")
    else:
        patches = list(patches_dir.glob("*.patch"))
        if not patches:
            errors.append(f"{discover_dir}/patches/: no .patch files found")
        for patch in patches:
            content = patch.read_text()
            if "---" not in content or "+++" not in content:
                errors.append(f"{patch.name}: invalid unified diff (missing --- or +++)")

    return errors


def validate_discover_report(repo_root: str) -> list[str]:
    """Check that the Discover report has required sections."""
    errors = []
    report = _find_discover_report(repo_root)
    if report is None:
        errors.append("discover-report.md not found (checked root and service subdirs)")
        return errors

    content = report.read_text()
    for section in ["Executive Summary", "Event Candidates", "Next Steps"]:
        if section not in content:
            errors.append(f"discover-report.md: missing '{section}' section")
    if "PII" not in content and "pii" not in content.lower():
        errors.append("discover-report.md: missing PII section")

    return errors


def validate_scan(repo_root: str) -> list[str]:
    """Check that scan mode did NOT generate artifacts (catalog is in-context only)."""
    errors = []
    root = Path(repo_root)
    artifact_dirs = ["schemas", "terraform", "contracts"]
    for dirname in artifact_dirs:
        if (root / dirname).exists():
            errors.append(f"{dirname}/ directory exists — scan mode should not generate artifacts")
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
        root = Path(repo_root)
        has_report = (root / "schema-report.md").exists()
        has_discover = _find_discover_dir(repo_root) is not None
        has_summary = (root / "executive-summary.md").exists()
        has_schemas = (root / "schemas").exists()
        has_terraform = (root / "terraform").exists()
        has_contracts = (root / "contracts").exists()

        if has_summary or (has_report and has_discover):
            mode = "combined"
        elif has_discover:
            mode = "discover"
        elif has_report:
            mode = "audit"
        elif not has_schemas and not has_terraform and not has_contracts:
            # No artifacts at all — could be scan mode
            mode = "scan"
        else:
            print("No output files detected. Run the schematizer skill first.")
            sys.exit(1)
        print(f"Auto-detected mode: {mode}\n")

    all_errors = []

    if mode in ("audit", "combined"):
        for name, validator in [
            ("Schemas", validate_schemas),
            ("Contracts", validate_contracts),
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

    if mode == "scan":
        errors = validate_scan(repo_root)
        if errors:
            print(f"  Scan Mode:")
            for e in errors:
                print(f"   - {e}")
            all_errors.extend(errors)
        else:
            print(f"  Scan Mode: OK (no artifacts generated, as expected)")

    print()
    if all_errors:
        print(f"Found {len(all_errors)} issue(s)")
        sys.exit(1)
    else:
        print("All validations passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
