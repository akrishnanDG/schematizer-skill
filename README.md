# Schematizer — Kafka Repo Analyzer

An AI-powered playbook that scans any repository to identify Kafka applications, extract schemas, tag PII fields, and generate Terraform to register schemas to Confluent Schema Registry.

Works with any AI coding assistant (Claude Code, Cursor, Copilot, Windsurf, etc.) or as a manual checklist for human-driven audits.

## What It Does

Point this at any codebase and it will:

1. **Discover** all Kafka producers and consumers across Java, Python, .NET, Go, and Node.js/TypeScript
2. **Detect risks** — `auto.register.schemas=true`, custom serializers bypassing Schema Registry
3. **Extract schemas** from data models in code (POJOs, dataclasses, structs, interfaces, etc.)
4. **Tag PII fields** with `confluent:tags` (`PII`, `PRIVATE`, `SENSITIVE`) for Confluent Stream Governance
5. **Generate Terraform** using `confluent_schema` + `confluent_tag` resources to register schemas and tags
6. **Produce a report** (`schema-report.md`) with findings, risks, PII inventory, and upgrade recommendations

## How to Use

`skill.md` is a structured playbook with detection patterns, classification rules, and output templates. It can be used in multiple ways:

---

### Option 1: Claude Code (AI CLI)

Install as a Claude Code skill:

```bash
# Global (available in all repos)
cp skill.md ~/.claude/skills/kafka-analyzer.md

# Or per-repo
mkdir -p /path/to/your/repo/.claude/skills
cp skill.md /path/to/your/repo/.claude/skills/kafka-analyzer.md
```

Open Claude Code in the target repo and prompt:

```
Analyze this repo for Kafka applications and generate schemas + Terraform
```

Other useful prompts:

```
# Scan only, no file generation
Scan this repo for Kafka applications and generate a report only

# Scope to one service
Analyze only the order-service/ directory for Kafka usage

# With schema validation (requires schema-registry MCP server)
Analyze this repo for Kafka, lint and validate all extracted schemas
```

---

### Option 2: Cursor / Windsurf / Copilot

Add `skill.md` to your project context:

**Cursor:**
- Open the repo in Cursor
- Add `skill.md` to the chat context (drag it in or use `@skill.md`)
- Prompt: `Follow the instructions in skill.md to analyze this repo for Kafka applications`

**Windsurf:**
- Open the repo in Windsurf
- Reference `skill.md` in the Cascade chat
- Prompt: `Using skill.md as your guide, scan this repo for Kafka producers and generate schemas + Terraform`

**GitHub Copilot Chat:**
- Open the repo in VS Code with Copilot
- Reference `skill.md`: `@workspace #file:skill.md Analyze this repo for Kafka applications following the phases in skill.md`

For all AI assistants, the key is to provide `skill.md` as context and instruct the assistant to follow it phase by phase.

---

### Option 3: ChatGPT / Claude.ai / Any LLM Chat

1. Copy the contents of `skill.md` into the system prompt or as the first message
2. Upload or paste your source files (build files, producer code, data models, config files)
3. Prompt: `Follow the phases in the instructions to analyze these files for Kafka usage and generate schemas + Terraform`

This works well for smaller repos. For large repos, focus on specific services:
- Upload `pom.xml` + producer class + data model + application.properties for one service at a time

---

### Option 4: Manual Audit (Human Checklist)

Use `skill.md` as a step-by-step checklist without any AI:

1. **Phase 1:** Search your repo for the build file patterns and dependency strings listed in section 1.1. Grep for the producer/consumer code patterns in section 1.2.
2. **Phase 2:** Grep for `auto.register.schemas=true` and custom serializer patterns listed in sections 2.1 and 1.4b.
3. **Phase 3:** For each producer found, locate the data model class and manually write the schema (JSON Schema, Avro, or Protobuf) using the type mapping tables in section 3.3. Scan field names against the PII patterns in section 3.3b.
4. **Phase 4:** Classify each producer into Category A/B/C/D/E using the table in section 4.
5. **Phase 5-6:** Create the schema files and Terraform configs using the templates in sections 5 and 6.
6. **Phase 7:** Write the report using the template in section 7.

The grep patterns, detection tables, classification rules, and Terraform templates in `skill.md` are all human-readable — no AI required.

---

### Option 5: CI/CD PR Gate (GitHub Actions / GitLab CI)

Block PRs that introduce Kafka risks. Two approaches — AI-powered (full analysis) or grep-only (zero AI cost).

**Approach A: Full AI analysis as PR gate (GitHub Actions + Claude Code)**

Runs the full skill on every PR that touches Kafka files. Posts the report as a PR comment and fails the check if risks are found.

```yaml
# .github/workflows/kafka-schema-check.yml
name: Kafka Schema Analysis

on:
  pull_request:
    paths:
      - '**/pom.xml'
      - '**/build.gradle'
      - '**/build.gradle.kts'
      - '**/package.json'
      - '**/go.mod'
      - '**/*.csproj'
      - '**/requirements.txt'
      - '**/pyproject.toml'
      - '**/*Producer*'
      - '**/*Consumer*'
      - '**/*Serializer*'
      - '**/*kafka*'
      - '**/*.avsc'
      - '**/*.proto'
      - '**/application*.properties'
      - '**/application*.yml'

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v4

      - name: Install Claude Code
        run: npm install -g @anthropic-ai/claude-code

      - name: Run Kafka Analyzer
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Follow the skill.md instructions to analyze this repo \
            for Kafka applications. Generate only schema-report.md — \
            no schemas or Terraform files." \
            --allowedTools "Glob,Grep,Read,Write"

      - name: Post report as PR comment
        if: always() && hashFiles('schema-report.md') != ''
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('schema-report.md', 'utf8');
            // Truncate if too long for a PR comment
            const body = report.length > 60000
              ? report.substring(0, 60000) + '\n\n... (truncated, see full report in artifacts)'
              : report;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: body
            });

      - name: Fail on critical risks
        if: hashFiles('schema-report.md') != ''
        run: |
          FAILED=0

          if grep -q "auto.register.schemas=true" schema-report.md; then
            echo "::error::auto.register.schemas=true detected — register schemas via Terraform instead"
            FAILED=1
          fi

          if grep -q "Category D" schema-report.md; then
            echo "::error::Kafka producer with no schema detected — adopt a schema-first approach"
            FAILED=1
          fi

          if grep -q "Category E" schema-report.md; then
            echo "::warning::Custom serializers without Schema Registry — add HeaderSchemaIdSerializer"
          fi

          if grep -q "Category B" schema-report.md; then
            echo "::warning::JSON producers without Schema Registry — upgrade to KafkaJsonSchemaSerializer + HeaderSchemaIdSerializer"
          fi

          exit $FAILED

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: kafka-schema-report
          path: schema-report.md
```

**Approach B: Grep-only PR gate (no AI, zero cost)**

Uses the detection patterns from `skill.md` directly as shell grep commands. No AI tokens consumed.

```yaml
# .github/workflows/kafka-lint.yml
name: Kafka Schema Lint

on:
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Block auto.register.schemas=true
        run: |
          if grep -ri "auto.register.schemas.*true" \
            --include="*.properties" --include="*.yml" --include="*.yaml" \
            --include="*.java" --include="*.py" --include="*.cs" \
            --include="*.go" --include="*.ts" --include="*.js" .; then
            echo "::error::auto.register.schemas=true found"
            echo "Register schemas via Terraform and set auto.register.schemas=false"
            exit 1
          fi

      - name: Warn on StringSerializer for values
        run: |
          if grep -ri "value.serializer.*StringSerializer\|value-serializer.*StringSerializer" \
            --include="*.properties" --include="*.yml" --include="*.yaml" \
            --include="*.java" .; then
            echo "::warning::StringSerializer used for values — use KafkaJsonSchemaSerializer + HeaderSchemaIdSerializer"
          fi

      - name: Warn on custom serializers without SR
        run: |
          CUSTOM=$(grep -rli "implements Serializer<\|ISerializer<\|IAsyncSerializer<" \
            --include="*.java" --include="*.cs" . 2>/dev/null || true)
          if [ -n "$CUSTOM" ]; then
            SR_REF=$(grep -li "schema.registry.url\|SchemaRegistryClient" $CUSTOM 2>/dev/null || true)
            if [ -z "$SR_REF" ]; then
              echo "::warning::Custom serializers without Schema Registry: $CUSTOM"
              echo "Add HeaderSchemaIdSerializer to inject schema ID into headers"
            fi
          fi

      - name: Warn on non-Confluent Kafka libraries
        run: |
          if grep -rq "kafka-python" --include="requirements.txt" --include="pyproject.toml" . 2>/dev/null; then
            echo "::warning::kafka-python detected — migrate to confluent-kafka"
          fi
          if grep -rq '"kafkajs"' --include="package.json" . 2>/dev/null; then
            echo "::warning::kafkajs detected — migrate to @confluentinc/kafka-javascript"
          fi

      - name: Warn on inline serialization without SR
        run: |
          if grep -rn "json\.dumps.*produce\|json\.dumps.*send" \
            --include="*.py" . 2>/dev/null; then
            echo "::warning::Inline json.dumps in Kafka produce — use confluent-kafka JSONSerializer"
          fi
          if grep -rn "JSON\.stringify.*send\|JSON\.stringify.*produce" \
            --include="*.ts" --include="*.js" . 2>/dev/null; then
            echo "::warning::Inline JSON.stringify in Kafka send — use Confluent serializer with SR"
          fi
          if grep -rn "json\.Marshal" --include="*.go" . 2>/dev/null | \
            grep -v "_test.go" | head -5; then
            echo "::warning::json.Marshal before Kafka Produce — use confluent-kafka-go serializer with SR"
          fi
```

**GitLab CI equivalent:**

```yaml
# .gitlab-ci.yml
kafka-schema-gate:
  stage: test
  rules:
    - changes:
        - "**/*kafka*"
        - "**/*Producer*"
        - "**/*Serializer*"
        - "**/pom.xml"
        - "**/build.gradle"
        - "**/package.json"
        - "**/go.mod"
        - "**/*.csproj"
        - "**/requirements.txt"
        - "**/application*.properties"
        - "**/application*.yml"
  script:
    - |
      FAILED=0

      echo "=== Checking for auto.register.schemas=true ==="
      if grep -ri "auto.register.schemas.*true" --include="*.properties" \
        --include="*.yml" --include="*.yaml" --include="*.java" \
        --include="*.py" --include="*.cs" --include="*.go" .; then
        echo "BLOCK: auto.register.schemas=true — use Terraform to register schemas"
        FAILED=1
      fi

      echo "=== Checking for custom serializers without SR ==="
      CUSTOM=$(grep -rli "implements Serializer<\|ISerializer<" \
        --include="*.java" --include="*.cs" . 2>/dev/null || true)
      if [ -n "$CUSTOM" ]; then
        SR_REF=$(grep -li "schema.registry.url\|SchemaRegistryClient" $CUSTOM 2>/dev/null || true)
        if [ -z "$SR_REF" ]; then
          echo "WARN: Custom serializers without SR: $CUSTOM"
          echo "Add HeaderSchemaIdSerializer to inject schema ID into headers"
        fi
      fi

      echo "=== Checking for non-Confluent libraries ==="
      grep -rq "kafka-python" --include="requirements.txt" . 2>/dev/null && \
        echo "WARN: kafka-python detected — migrate to confluent-kafka" || true
      grep -rq '"kafkajs"' --include="package.json" . 2>/dev/null && \
        echo "WARN: kafkajs detected — migrate to @confluentinc/kafka-javascript" || true

      exit $FAILED
  allow_failure: false
```

**What each approach catches:**

| Check | Grep-only | AI-powered |
|-------|-----------|------------|
| `auto.register.schemas=true` | Blocks PR | Blocks PR + shows in report |
| `StringSerializer` for values | Warns | Warns + recommends KafkaJsonSchemaSerializer |
| Custom serializers without SR | Warns | Warns + recommends HeaderSchemaIdSerializer |
| Non-Confluent libraries (kafka-python, kafkajs) | Warns | Warns + shows migration path |
| Inline serialization (json.dumps, JSON.stringify) | Warns | Warns + extracts schema from data model |
| PII field detection | Not available | Tags fields with confluent:tags |
| Schema extraction | Not available | Generates schema files |
| Terraform generation | Not available | Generates confluent_schema resources |
| Consumer impact analysis | Not available | Cross-references producers and consumers |

---

### What Happens During Analysis

Regardless of which tool you use, the analysis follows these phases:

1. Search for build files (`pom.xml`, `package.json`, `go.mod`, `*.csproj`, etc.)
2. Identify Kafka dependencies and producer/consumer code patterns
3. Extract topic names from source code
4. Detect serializer types and custom serializers
5. Flag `auto.register.schemas=true` occurrences
6. Read data model classes and infer schemas
7. Tag PII fields with `confluent:tags`
8. Generate schema files, Terraform configs, and a detailed report

### Output Structure

The analysis produces 3 deliverables:

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

### After the Analysis

1. **Review the report** — `schema-report.md` has the full findings, risks, and recommendations
2. **Review extracted schemas** — check `schemas/` for accuracy, especially PII tags
3. **Apply Terraform** — see [Applying the Terraform](#applying-the-terraform) below
4. **Follow upgrade recommendations** — the report has per-app instructions with code snippets

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

- **Any AI coding assistant** (Claude Code, Cursor, Windsurf, Copilot) — or a human following the checklist
- **Terraform** — to apply the generated configs
- **Confluent Schema Registry** — target for schema registration

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

The analyzer recommends different approaches based on the producer category:

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

When using AI assistants, expect roughly:

| Repo Size | Estimated Tokens |
|-----------|-----------------|
| Small (1-3 Kafka apps) | 100-150K |
| Medium (5-10 apps) | 200-400K |
| Large monorepo (20+ apps) | 500K-1M |

Tips to reduce token usage:
- Use a smaller/faster model (e.g., Sonnet instead of Opus in Claude Code)
- Scope to a specific directory instead of the whole repo
- Two-pass: first scan and report, then generate Terraform for selected services
