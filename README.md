# Schematizer — Kafka Repo Analyzer

A Claude Code skill that scans any repository to identify Kafka applications, extract schemas, tag PII fields, and generate Terraform to register schemas to Confluent Schema Registry.

## What It Does

Point this skill at any codebase and it will:

1. **Discover** all Kafka producers and consumers across Java, Python, .NET, Go, and Node.js/TypeScript
2. **Detect risks** — `auto.register.schemas=true`, custom serializers bypassing Schema Registry
3. **Extract schemas** from data models in code (POJOs, dataclasses, structs, interfaces, etc.)
4. **Tag PII fields** with `confluent:tags` (`PII`, `PRIVATE`, `SENSITIVE`) for Confluent Stream Governance
5. **Generate Terraform** using `confluent_schema` + `confluent_tag` resources to register schemas and tags
6. **Produce a report** (`schema-report.md`) with findings, risks, PII inventory, and upgrade recommendations

## How to Use

### 1. Install the skill

Copy `skill.md` to your Claude Code skills directory:

```bash
# Global (available in all repos)
cp skill.md ~/.claude/skills/kafka-analyzer.md

# Or per-repo
mkdir -p /path/to/your/repo/.claude/skills
cp skill.md /path/to/your/repo/.claude/skills/kafka-analyzer.md
```

### 2. Run it

Open Claude Code in the target repo and use one of these prompts:

**Full analysis (scan + schemas + Terraform + report):**
```
Analyze this repo for Kafka applications and generate schemas + Terraform
```

**Scan only (report without generating files):**
```
Scan this repo for Kafka applications and generate a report only, no schemas or Terraform
```

**Scope to a specific service:**
```
Analyze only the order-service/ directory for Kafka usage
```

**With MCP server for schema validation:**
```
Analyze this repo for Kafka, lint and validate all extracted schemas
```

### 3. What happens

Claude Code will:
1. Search for build files (`pom.xml`, `package.json`, `go.mod`, `*.csproj`, etc.)
2. Identify Kafka dependencies and producer/consumer code patterns
3. Extract topic names from source code
4. Detect serializer types and custom serializers
5. Flag `auto.register.schemas=true` occurrences
6. Read data model classes and infer schemas
7. Tag PII fields with `confluent:tags`
8. Generate schema files, Terraform configs, and a detailed report

### 4. After the analysis

1. **Review the report** — `schema-report.md` has the full findings, risks, and recommendations
2. **Review extracted schemas** — check `schemas/` for accuracy, especially PII tags
3. **Apply Terraform** — see [Applying the Terraform](#applying-the-terraform) below
4. **Follow upgrade recommendations** — the report has per-app instructions with code snippets

### 3. Review outputs

The skill creates 3 deliverables in the target repo:

```
your-repo/
├── schema-report.md                # Analysis report
├── schemas/
│   ├── schema.yaml                 # Schema project config
│   ├── avro/
│   │   └── {topic}-value.avsc
│   ├── json/
│   │   └── {topic}-value.json
│   └── proto/
│       └── {topic}-value.proto
└── terraform/
    ├── providers.tf
    ├── variables.tf
    ├── tags.tf                      # confluent_tag resources (PII, PRIVATE, etc.)
    ├── schemas.tf                   # Active schema resources (depends_on tags)
    ├── flagged-auto-register.tf     # Commented-out flagged resources
    ├── outputs.tf
    └── import.sh                    # Import script for existing schemas
```

## What It Detects

### Languages Supported

| Language | Build Files | Producer Patterns | Consumer Patterns |
|----------|------------|------------------|------------------|
| Java | pom.xml, build.gradle | KafkaTemplate, KafkaProducer, KStream, StreamBridge | @KafkaListener, KafkaConsumer |
| Python | requirements.txt, pyproject.toml | Producer(), .produce() | Consumer(), .poll() |
| .NET | *.csproj | ProducerBuilder, ProduceAsync | ConsumerBuilder, .Consume() |
| Go | go.mod | kafka.NewProducer, .Produce() | kafka.NewConsumer, .ReadMessage() |
| Node/TS | package.json | producer.send(), kafka.producer() | consumer.run(), eachMessage |

### Producer Categories

Each producer is classified into a category that drives the recommended action:

| Category | What It Means | Action Taken |
|----------|--------------|-------------|
| **A: Compliant** | Uses Confluent serializer + Schema Registry | Schema extracted to Terraform |
| **B: Schema in code, no SR** | Has data models but uses StringSerializer or similar (JSON) | Schema extracted + recommend `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` |
| **C: Auto-register** | Has `auto.register.schemas=true` | Schema in commented-out Terraform + risk flagged |
| **D: No schema** | Raw strings/bytes, no data model | Flagged in report |
| **E: Custom serializer** | Custom `Serializer<T>` impl, inline `json.dumps`, `json.Marshal`, `fastavro`, `proto.Marshal`, etc. | Schema extracted + recommend adding `HeaderSchemaIdSerializer` (keep custom serializer) |

### PII Detection

Field names are scanned against known PII patterns and tagged with `confluent:tags`:

| Pattern | Tags Applied |
|---------|-------------|
| email, phone, mobile | `PII` |
| ssn, credit_card, passport | `PII`, `PRIVATE` |
| name, address, date_of_birth | `PII` |
| salary, gender, medical | `SENSITIVE` |
| password, secret, api_key | `PRIVATE` |

Tags are added inline to schemas:
- **Avro/JSON Schema:** `"confluent:tags": ["PII"]`
- **Protobuf:** `[(confluent.field_meta).tags = "PII"]`

These tags must be pre-created in the SR catalog — the Terraform includes `confluent_tag` resources that are created before schemas (`depends_on`).

## Prerequisites

### Required

- **Claude Code** — the CLI tool from Anthropic

### Optional (enhances the analysis)

- **schema-registry MCP server** — enables automated schema linting, validation, and inference
  - `schema_lint` — validates schemas for quality issues (missing defaults, PII, naming)
  - `schema_validate` — checks backward compatibility against live Schema Registry
  - `schema_infer` — generates schemas from sample JSON data files
  - `schema_init` — creates schema project configuration

Without the MCP server, the skill still works — it just performs manual validation and notes in the report which automated checks were skipped.

## Applying the Terraform

After reviewing the outputs:

```bash
cd terraform

# If schemas already exist in Schema Registry, import them first:
chmod +x import.sh
# Edit import.sh to set your SR cluster ID
export IMPORT_SCHEMA_REGISTRY_API_KEY=<key>
export IMPORT_SCHEMA_REGISTRY_API_SECRET=<secret>
export IMPORT_SCHEMA_REGISTRY_REST_ENDPOINT=<url>
./import.sh

# Initialize and apply
terraform init

# Set variables
export TF_VAR_schema_registry_id=lsrc-abc123
export TF_VAR_schema_registry_rest_endpoint=https://psrc-xxxxx.us-east-1.aws.confluent.cloud
export TF_VAR_schema_registry_api_key=<key>
export TF_VAR_schema_registry_api_secret=<secret>

terraform plan
terraform apply
```

Note: `confluent_tag` resources (PII, PRIVATE, SENSITIVE) are created first automatically via `depends_on`.

## Report Contents

The generated `schema-report.md` includes:

- **Executive Summary** — counts of apps, topics, schemas, risks, PII fields
- **Applications Discovered** — table of all Kafka apps with language, role, topics, category
- **Risks** — `auto.register.schemas=true` occurrences and custom serializers without SR
- **Producer Upgrade Recommendations** — per-app instructions with format-specific guidance
- **Schemas Extracted** — all schemas with source and file path
- **PII Fields Detected** — inventory of all PII-tagged fields with tags and rationale
- **Terraform Resources** — what was generated and what's commented out
- **Consumer Impact Notes** — which consumers may be affected by serializer changes
- **Next Steps** — checklist for the team

## Upgrade Recommendations

The skill recommends different approaches based on the producer category:

### Category B — JSON producers without SR

Replace the serializer entirely. Payload stays clean JSON, consumers don't break.

| Current State | Recommended |
|--------------|-------------|
| `StringSerializer` + JSON | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` |
| Spring `JsonSerializer` | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` |
| `kafka-python` + `json.dumps` | `confluent-kafka` `JSONSerializer` + `HeaderSchemaIdSerializer` |
| `kafkajs` + `JSON.stringify` | `@confluentinc/kafka-javascript` with SR schema support |
| Go `json.Marshal` | `confluent-kafka-go` JSON serializer + header mode |
| .NET `JsonConvert` | `Confluent.SchemaRegistry.Serdes.Json.JsonSerializer<T>` + header mode |

### Category E — Custom serializers (any format)

Do NOT replace the custom serializer. Add only `HeaderSchemaIdSerializer` to inject the schema ID into Kafka headers. The custom serializer keeps producing the exact same payload bytes. Consumers don't break.

| Current State | Recommended |
|--------------|-------------|
| Custom `Serializer<T>` (JSON, Avro, or Protobuf) | Keep custom serializer + add `HeaderSchemaIdSerializer` |
| Inline `fastavro` / `DatumWriter` (Avro) | Keep custom serializer + add `HeaderSchemaIdSerializer` |
| Inline `proto.Marshal` / `toByteArray()` (Protobuf) | Keep custom serializer + add `HeaderSchemaIdSerializer` |

**Why this distinction?**

- **Category B (JSON):** The data is JSON. `KafkaJsonSchemaSerializer` produces the same clean JSON output, so swapping the serializer is safe. `HeaderSchemaIdSerializer` puts the schema ID in headers instead of the payload.

- **Category E (Custom):** Replacing a custom serializer with a Confluent serializer (e.g., `KafkaAvroSerializer`) changes the payload encoding or wire format — this breaks existing consumers. Adding only `HeaderSchemaIdSerializer` keeps the payload byte-identical while adding SR governance via headers.

## Token Usage Estimates

| Repo Size | Estimated Tokens |
|-----------|-----------------|
| Small (1-3 Kafka apps) | 100-150K |
| Medium (5-10 apps) | 200-400K |
| Large monorepo (20+ apps) | 500K-1M |

Tips to reduce cost:
- Use Sonnet instead of Opus (`/model sonnet`)
- Scope to a specific directory: "Analyze only the `order-service/` directory"
- Two-pass: "First just scan and report, don't generate Terraform yet"
