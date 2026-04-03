---
name: schematizer
description: Analyze any backend repository for Kafka event streaming — audit existing Kafka usage (extract schemas, detect risks, generate Terraform) and discover new event opportunities (find domain models, generate recommendations, schema stubs, and code patches). Use this skill when a user asks to analyze a repo for Kafka, extract schemas, audit producer/consumer configurations, generate Terraform for Schema Registry, or discover where Kafka events should be added.
---

# Schematizer — Kafka Schema & Event Discovery Tool

Analyze any backend repository for Kafka event streaming: audit existing Kafka usage, discover new event opportunities, or both.

## When to Use

Invoke this skill when:
- A user asks to analyze, audit, or scan a repo for Kafka usage (**Audit mode**)
- A user asks to discover where Kafka events should be added (**Discover mode**)
- A user asks for a full/comprehensive Kafka analysis (**Combined mode**)
- A user wants schemas, Terraform, event recommendations, or code patches

## Modes

### Audit Mode — "What Kafka do you already have?"

Scans repos with **existing** Kafka producers/consumers. Extracts schemas, detects risks (auto-register, custom serializers), generates Terraform for Schema Registry, produces an analysis report.

**Trigger phrases:** analyze, audit, scan for Kafka, extract schemas, generate Terraform, check Kafka config

**Outputs:** `schemas/`, `terraform/`, `schema-report.md`

**How:** Read and follow `skill-audit.md` (Phases 0–7).

### Discover Mode — "Where should you add Kafka?"

Scans repos to find domain models, DTOs, entities, and service methods that are strong candidates for Kafka event publication. Produces ranked recommendations, schema stubs, and code patches.

**Trigger phrases:** discover, find event candidates, where should I add Kafka, instrument with Kafka, what should I stream

**Outputs:** `discover/kafka_recommendations.yaml`, `discover/kafka_schemas.yaml`, `discover/patches/`, `discover-report.md`

**How:** Read and follow `skill-discover.md` (Phases D0–D5).

### Combined Mode — Full Analysis

Runs both modes and cross-references findings.

**Trigger phrases:** full analysis, comprehensive Kafka analysis, audit and discover

**How:**

1. **Run Audit first** — Read and follow `skill-audit.md` (Phases 0–7)
2. **Pass Audit catalog to Discover** — The app catalog from Audit Phase 1.5 identifies services already producing/consuming Kafka. Pass this context to Discover so it:
   - Skips services already fully instrumented (Category A)
   - For partially instrumented services (B/C/D/E), looks for *additional* event candidates not already being produced
   - For un-instrumented services, runs full discovery
3. **Run Discover** — Read and follow `skill-discover.md` (Phases D0–D5) with the Audit context
4. **Generate combined summary** — Create `executive-summary.md` linking both reports

---

## Mode Selection

When the user's intent is ambiguous, choose the mode based on what the repo contains:

1. **Quick check:** Search for Kafka client libraries in build files (see Audit Phase 1.1)
2. **If Kafka libraries are found** → Default to **Audit mode**
3. **If no Kafka libraries are found** → Default to **Discover mode**
4. **If Kafka libraries are found but coverage seems partial** → Suggest **Combined mode**

Always confirm the mode with the user if uncertain.

---

## Output Structure

### Audit Only
```
{repo}/
  schema-report.md
  schemas/
  terraform/
```

### Discover Only
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
  terraform/
  discover-report.md
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
| `discover/kafka_recommendations.yaml` | Discover | Ranked candidates for review |
| `discover/kafka_schemas.yaml` | Discover | Schema stubs for new events |
| `discover/patches/` | Discover | Code patches to add producers |
```

---

## Language Support

Both modes support these languages:

| Language | Build Files | Frameworks |
|----------|------------|------------|
| Java | `pom.xml`, `build.gradle` | Spring Kafka, kafka-clients, Kafka Streams |
| Python | `requirements.txt`, `pyproject.toml` | confluent-kafka, kafka-python, Pydantic, Django, FastAPI |
| .NET | `*.csproj` | Confluent.Kafka, EF Core, MediatR |
| Go | `go.mod` | confluent-kafka-go, sarama, GORM |
| Node/TS | `package.json` | kafkajs, @confluentinc/kafka-javascript, NestJS, Prisma |
| PHP | `composer.json` | php-rdkafka, Laravel, Symfony, Doctrine |

---

## Independent Installation

Each sub-skill can be installed and used independently:

**Audit only:**
```bash
cp skill-audit.md ~/.claude/skills/kafka-audit.md
# or
cp skill-audit.md /path/to/repo/.claude/skills/kafka-audit.md
```

**Discover only:**
```bash
cp skill-discover.md ~/.claude/skills/kafka-discover.md
# or
cp skill-discover.md /path/to/repo/.claude/skills/kafka-discover.md
```

**Both (with orchestrator):**
```bash
cp skill.md skill-audit.md skill-discover.md ~/.claude/skills/
```
