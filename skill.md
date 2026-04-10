---
name: schematizer
description: Analyze any backend repository for Kafka event streaming — scan and classify Kafka usage, audit existing producers (extract schemas, detect risks, generate Terraform), and discover new event opportunities. Use this skill when a user asks to analyze a repo for Kafka, extract schemas, audit configurations, generate Terraform for Schema Registry, or discover where Kafka events should be added.
---

# Schematizer — Kafka Schema & Event Discovery Tool

Analyze any backend repository for Kafka event streaming: scan, audit, discover, or all three.

## When to Use

Invoke this skill when:
- A user asks to analyze, audit, or scan a repo for Kafka usage
- A user asks to discover where Kafka events should be added
- A user wants schemas, Terraform, event recommendations, or code patches

## Modes

### Scan Mode — "What's the current state?"

Quick classification of all Kafka apps in a repo. Produces a structured catalog with categories, risks, and PII inventory. No artifacts generated.

**Trigger phrases:** scan, quick check, what Kafka do we have, classify, categorize

**Outputs:** App catalog (in-context) with category assignments

**How:** Read and follow `skill-scan.md`.

### Audit Mode — "Fix what's broken"

Full scan + artifact generation: schemas, Terraform, comprehensive report, CI/CD gate.

**Trigger phrases:** audit, analyze, extract schemas, generate Terraform, full report

**Outputs:** `schemas/`, `terraform/`, `schema-report.md`

**How:**
1. Read and follow `skill-scan.md` (Phases 0–4). Output: app catalog.
2. Pass catalog to `skill-audit-generate.md`. Output: schemas, Terraform, report.

### Discover Mode — "Where should you add Kafka?"

Scans repos to find domain models, entities, and service methods that are strong candidates for Kafka event publication.

**Trigger phrases:** discover, find event candidates, where should I add Kafka, what should I stream

**Default outputs:** `discover/kafka_recommendations.yaml`, `discover/kafka_schemas.yaml`
**Opt-in outputs:** `discover/patches/` (if user asks for patches), `discover-report.md` (if user asks for report)

**How:** Read and follow `skill-discover.md` (Phases D0–D5). Phases D4.4 and D5 are opt-in.

### Combined Mode — Full Analysis

Runs scan, audit, and discover — cross-references findings.

**Trigger phrases:** full analysis, comprehensive Kafka analysis, audit and discover

**How:**
1. **Scan** — Read and follow `skill-scan.md` (Phases 0–4). Output: app catalog.
2. **Audit** — Pass catalog to `skill-audit-generate.md`. Output: schemas, Terraform, report.
3. **Discover** — Pass catalog + `schema-report.md` context to `skill-discover.md` (Phases D0–D5). Discover uses the catalog to:
   - For Category A services: scan for *additional* events beyond what's already produced
   - For B/C/D/E services: look for *additional* events not already being produced
   - For un-instrumented services: run full discovery
4. **Executive Summary** — Generate `executive-summary.md` linking both reports.

**If scan finds zero Kafka applications:** Skip Audit. Run Discover on all services.

**Partial failures:** If Audit fails (e.g., context exhausted), partial outputs are still usable. Do not run Discover until Audit completes or is explicitly skipped. To resume: check which output files exist.

---

## Mode Selection

When intent is ambiguous:
1. Search build files for Kafka dependencies
2. **Found in all services** → default to **Audit**
3. **Found in none** → default to **Discover**
4. **Found in some but not all** → suggest **Combined**

Always confirm with the user if uncertain.

---

## Output Structure

### Scan Only
```
(no files — catalog is in-context output)
```

### Audit
```
{repo}/
  schema-report.md
  schemas/
  terraform/
    ci/schema-lint.yml
```

### Discover (default)
```
{repo}/
  discover/
    kafka_recommendations.yaml
    kafka_schemas.yaml
```

### Discover (with opt-ins: "include patches and report")
```
{repo}/
  discover-report.md
  discover/
    kafka_recommendations.yaml
    kafka_schemas.yaml
    patches/
```

### Combined
```
{repo}/
  schema-report.md
  schemas/
  contracts/
  terraform/
    ci/schema-lint.yml
  discover/
    kafka_recommendations.yaml
    kafka_schemas.yaml
    patches/
  executive-summary.md
```

---

## Combined Mode: Executive Summary Template

When running in combined mode, after both Audit and Discover complete, generate `executive-summary.md`:

```markdown
# Kafka Analysis — Executive Summary

> Generated on {date}
> Repository: {repo_name}
> Mode: Combined (Audit + Discover)

---

## Overview

| Dimension | Count |
|-----------|-------|
| **Audit — Existing Kafka** | |
| Kafka applications found | {N} |
| Producers | {N} |
| Consumers | {N} |
| Schemas extracted | {N} |
| Risks found | {N} |
| **Discover — New Opportunities** | |
| Services scanned | {N} |
| Event candidates found | {N} |
| High-confidence candidates | {N} |
| PII fields (total) | {N} |

---

## Key Findings

### Existing Kafka Health
- {summary of Audit findings: compliant producers, risks, category breakdown}
- See full details: [`schema-report.md`](schema-report.md)

### New Event Opportunities
- {summary of Discover findings: top candidates, business value}
- See full details: [`discover-report.md`](discover-report.md)

### Overlap
- {N} services already have Kafka producers
- {N} of those have additional event candidates identified by Discover
- {N} services have no Kafka yet — all candidates are new

---

## Recommended Action Plan

1. **Immediate — Fix risks** (from Audit)
   - Disable `auto.register.schemas=true` in {N} producers
   - Replace {N} custom serializers with Confluent serializers
2. **Short-term — Register schemas** (from Audit)
   - Run `terraform apply` to register {N} schemas via IaC
3. **Medium-term — Add new events** (from Discover)
   - Review `discover/kafka_recommendations.yaml` — approve top candidates
   - Apply patches and register new schemas
4. **Ongoing — Governance**
   - Add schema validation to CI/CD
   - Monitor PII fields via Stream Governance tags

---

## Output Files

| File | Source | Purpose |
|------|--------|---------|
| `schema-report.md` | Audit | Full audit findings |
| `schemas/` | Audit | Extracted schema files |
| `terraform/` | Audit | Terraform for schema registration |
| `discover-report.md` | Discover | Event discovery findings |
| `discover/kafka_recommendations.yaml` | Discover | Ranked candidates |
| `discover/kafka_schemas.yaml` | Discover | Schema stubs for new events |
| `discover/patches/` | Discover | Code patches to add producers |
```
