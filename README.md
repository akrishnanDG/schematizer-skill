# Schematizer — Kafka Schema & Event Discovery Tool

AI-powered skill that scans any repository to **audit existing Kafka usage** and **discover new event opportunities**. Extracts schemas, generates data contracts with PII tags, produces Terraform, and creates ready-to-apply code patches.

Works with Claude Code, Cursor, Windsurf, Copilot, or as a manual checklist.

## Skill Architecture

```
skill.md                  (2K tokens)   Orchestrator — routes to the right mode
skill-scan.md             (3K tokens)   Detection + classification (Phases 0-4)
skill-audit-generate.md   (9K tokens)   Schema/contract/Terraform generation (Phases 5-8)
skill-discover.md         (3K tokens)   Event discovery (Phases D0-D5)
```

## Five Modes

| Mode | What it does | Cost | Time |
|------|-------------|------|------|
| **PR** | Scan only changed files for governance risks | ~$0.01 | <1 min |
| **Scan** | Classify all Kafka apps, no artifacts | ~$0.02 | <1 min |
| **Audit** | Scan + schemas + contracts + Terraform + report | ~$0.20-0.70 | 3-5 min |
| **Discover** | Find where to add Kafka events (default: YAML only) | ~$0.10-0.20 | 2-3 min |
| **Combined** | Audit + Discover + executive summary | ~$0.30-1.00 | 5-8 min |

## Installation

```bash
# Claude Code — install globally
cp skill.md skill-scan.md skill-audit-generate.md skill-discover.md ~/.claude/skills/

# Or per-repo
mkdir -p /path/to/repo/.claude/skills
cp skill.md skill-scan.md skill-audit-generate.md skill-discover.md /path/to/repo/.claude/skills/

# CLI (no installation needed)
claude --model claude-sonnet-4-6 \
  --add-dir /path/to/repo \
  --append-system-prompt "$(cat skill-scan.md)" \
  --append-system-prompt "$(cat skill-audit-generate.md)" \
  -p "Analyze this repo for Kafka applications. Generate schemas, Terraform, and a full report."
```

## Usage

```bash
# PR mode — scan only changed files
"Scan this PR for Kafka governance risks"

# Scan mode — quick governance scorecard
"Scan this repo for Kafka applications and classify them"

# Audit mode — full analysis
"Analyze this repo for Kafka applications. Generate schemas, Terraform, and a full report."

# Discover mode — find event candidates (fast — YAML only)
"Discover where Kafka events should be added in the loan-origination service"

# Discover with opt-in patches and report
"Discover where Kafka events should be added. Include patches and report."

# Combined mode
"Run a full Kafka analysis — audit existing services and discover new event opportunities"
```

## Output Structure

### Audit
```
your-repo/
├── schema-report.md                    # Analysis report
├── scripts/validate-schemas.sh         # Local validation script
├── schemas/
│   ├── schema.yaml                     # Schema project manifest
│   ├── avro/{topic}-value.avsc         # Pure schema — no tags
│   └── json/{topic}-value.json         # Pure schema — no tags
├── contracts/
│   └── {topic}-value.contract.json     # PII tags + rules (separate from schema)
└── terraform/
    ├── providers.tf                    # Confluent provider v2.x
    ├── variables.tf
    ├── tags.tf                         # confluent_tag definitions
    ├── schemas.tf                      # confluent_schema (registered first)
    ├── contracts.tf                    # confluent_tag_binding (applied after schemas)
    ├── flagged-auto-register.tf        # Commented-out flagged resources
    ├── outputs.tf
    ├── import.sh                       # Import existing schemas
    └── ci/schema-lint.yml              # GitHub Actions PR gate
```

### Discover (default)
```
your-repo/
└── discover/
    ├── kafka_recommendations.yaml      # Ranked candidates (pending_review)
    └── kafka_schemas.yaml              # Schema stubs
```

### Discover (with opt-ins)
```
your-repo/
├── discover-report.md                  # Discovery report (opt-in)
└── discover/
    ├── kafka_recommendations.yaml
    ├── kafka_schemas.yaml
    └── patches/                        # Code patches (opt-in)
        └── {service}-kafka-producer.patch
```

## Key Design Decisions

### Schema/Contract Separation

Schemas contain **only** the data definition — no `confluent:tags`, no `metadata`, no `ruleset`. Governance (PII tags, encryption rules) lives in separate contract files (`contracts/{subject}.contract.json`).

Why: schemas and governance have different lifecycles. Your schema team evolves the data model; your compliance team manages tags. They don't step on each other. Terraform registers schemas first, then applies tag bindings.

### C-App vs C-Connector

`auto.register.schemas=true` means different things depending on where it appears:

| Context | Classification | Action |
|---------|---------------|--------|
| Application producer config | **C-App** — misconfiguration | Disable, register via Terraform |
| Kafka Connect source connector | **C-Connector** — by design | Apply governance (compatibility mode, subject naming, PII tags via contracts) |

Debezium, JDBC Source, S3 Source, and other source connectors *require* auto-register. The skill does NOT recommend disabling it for connectors.

### Deterministic Templates

Schema generation is template-based, not LLM-inferred:
- **camelCase** for JSON Schema and Avro fields, **snake_case** for Protobuf
- **Descriptions** on every field (mandatory)
- **Defaults** on all optional fields (mandatory for schema evolution)
- **Avro enums**: `UNKNOWN` as first symbol with default
- **`additionalProperties: false`** always for JSON Schema
- **Timestamps**: `date-time` (JSON), `timestamp-millis` (Avro), `google.protobuf.Timestamp` (Protobuf)

### CSFLE Opt-In

ENCRYPT rules and KEK registration are only generated when explicitly requested. Default contracts contain tag bindings only — no `ruleSet`, no KMS dependency. Tags alone enable Stream Governance visibility, audit, and policy enforcement.

### Discover Patches Opt-In

Patches and reports are slow to generate (~40% of runtime). Default discover produces only `kafka_recommendations.yaml` + `kafka_schemas.yaml`. Say "include patches" or "include report" to get the full output.

## Producer Categories (Audit)

| Category | Criteria | Action |
|----------|----------|--------|
| **A: Compliant** | Confluent serializer + SR + `auto.register=false` | Extract schema to Terraform |
| **A→Header** | Already on SR, migrating to header-based schema ID | Add `HeaderSchemaIdSerializer` |
| **B: No SR** | Has data models but uses `StringSerializer`/`json.dumps` | Extract schema + upgrade recommendation |
| **C-App** | Application with `auto.register.schemas=true` | Disable, register via Terraform |
| **C-Connector** | Kafka Connect source connector with auto-register | Apply governance, don't disable |
| **D: No schema** | Raw strings/bytes, unrecoverable field names | Flag in report |
| **E: Custom serializer** | Implements `Serializer<T>` or inline serialization without SR | Extract schema + consumer-first migration |

## Per-Language Consumer Deserializers

The skill generates hybrid deserializer patterns for Category E migrations (consumers must handle both old and new formats during transition):

| Language | Pattern | Standard deserializer (post-migration) |
|----------|---------|---------------------------------------|
| Java | Header-inspecting `Deserializer<T>` | `KafkaJsonSchemaDeserializer` |
| Python | Callable with header fallback | `confluent_kafka.schema_registry.json_schema.JSONDeserializer` |
| .NET | Custom `IDeserializer<T>` | `Confluent.SchemaRegistry.Serdes.JsonDeserializer<T>` |
| Go | Header check helper function | `confluent-kafka-go/v2/schemaregistry/serde/jsonschema` |
| Node.js | Message header inspection | `@confluentinc/kafka-javascript` SR deserializer |

`CompositeDeserializer` is Java-only. Each language has its own dual-format implementation.

## Local Validation

The skill generates `scripts/validate-schemas.sh` that validates output locally:
- JSON Schema meta-validation via `check-jsonschema`
- Avro validation via `schema-registry-maven-plugin`
- Contract file validation (subject, tags, field paths)
- Schema purity check (no `confluent:tags` in schema files)

## Languages Supported

| Language | Build Files | Audit | Discover |
|----------|------------|-------|---------|
| Java / Kotlin / Scala | pom.xml, build.gradle | Spring Kafka, kafka-clients, KStream, Kafka Connect | JPA entities, Spring services |
| Python | requirements.txt, pyproject.toml | confluent-kafka, kafka-python | Pydantic, Django, dataclasses |
| .NET | *.csproj | Confluent.Kafka | EF Core, MediatR, records |
| Go | go.mod | confluent-kafka-go, sarama | Structs with json tags, GORM |
| Node/TS | package.json | kafkajs, @confluentinc/kafka-javascript | TypeScript interfaces, Prisma |
| PHP | composer.json | php-rdkafka | Doctrine, Laravel, Symfony |

## Minimum Client Versions

> Java CP 8.0+, Python v2.10.1+, .NET v2.10.1+, Go v2.10.1+, Node v1.3.2+

## Evals

```bash
# Run validation against skill output
./scripts/run_evals.sh /path/to/output/repo audit
./scripts/run_evals.sh /path/to/output/repo discover

# Eval definitions in evals/
ls evals/
```

## Known Limitations

| Limitation | Mitigation |
|------------|-----------|
| Patch generation is fragile | Verify with `git apply --check`. Expect hand-fixes. |
| PII detection is name-based | Review tags. Add `PUBLIC` to false positives. |
| Large repos may exhaust context | Scope to specific services. |
| Non-deterministic output across runs | Template-based generation reduces variance but doesn't eliminate it. |
| No live SR compatibility check | Run `scripts/validate-schemas.sh` locally before `terraform apply`. |
