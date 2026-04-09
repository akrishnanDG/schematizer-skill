# Schematizer — Kafka Schema & Event Discovery Tool

An AI-powered playbook that scans any repository to **audit existing Kafka usage** and **discover new event opportunities**. Extracts schemas, tags PII fields, generates Terraform, and produces ready-to-apply code patches.

Works with any AI coding assistant (Claude Code, Cursor, Copilot, Windsurf, etc.) or as a manual checklist for human-driven audits.

## Two Modes

### Audit Mode — "What Kafka do you already have?"

Point this at any codebase with Kafka and it will:

1. **Find** all Kafka producers and consumers across Java, Python, .NET, Go, Node.js/TypeScript, and PHP
2. **Detect risks** — `auto.register.schemas=true`, custom serializers bypassing Schema Registry
3. **Extract schemas** from data models in code (POJOs, dataclasses, structs, interfaces, etc.)
4. **Tag PII fields** with `confluent:tags` (`PII`, `PRIVATE`, `SENSITIVE`) for Confluent Stream Governance
5. **Generate Terraform** using `confluent_schema` + `confluent_tag` resources to register schemas and tags
6. **Produce a report** (`schema-report.md`) with findings, risks, PII inventory, and upgrade recommendations

### Discover Mode — "Where should you add Kafka?"

Point this at any backend codebase (with or without Kafka) and it will:

1. **Scan** for domain models, DTOs, entities, value objects, and event enums across 7 languages
2. **Identify** service methods on the write path (create, update, delete, save) as insertion points
3. **Rank** candidates by business value using scoring heuristics
4. **Reason** about each candidate — what business question it answers, recommended topic name, downstream consumers
5. **Generate** a human-reviewable plan (`kafka_recommendations.yaml`), schema stubs (`kafka_schemas.yaml`), and code patches (`.patch` files)
6. **Produce a report** (`discover-report.md`) with ranked candidates and next steps

### Combined Mode — Full Analysis

Runs both modes and cross-references findings. Produces an `executive-summary.md` linking Audit and Discover results.

---

## How to Use

The tool is a set of structured playbooks (`skill.md`, `skill-audit.md`, `skill-discover.md`) with detection patterns, classification rules, and output templates. Multiple ways to use them:

### Option 1: Claude Code (AI CLI)

Install as Claude Code skills:

```bash
# All modes (recommended)
cp skill.md skill-audit.md skill-discover.md ~/.claude/skills/

# Or per-repo
mkdir -p /path/to/your/repo/.claude/skills
cp skill.md skill-audit.md skill-discover.md /path/to/your/repo/.claude/skills/

# Or just one mode
cp skill-audit.md ~/.claude/skills/kafka-audit.md       # Audit only
cp skill-discover.md ~/.claude/skills/kafka-discover.md  # Discover only
```

Open Claude Code in the target repo and prompt:

```
# Audit mode
Analyze this repo for Kafka applications and generate schemas + Terraform

# Discover mode
Discover where Kafka events should be added in this repo

# Combined mode
Run a full Kafka analysis — audit existing usage and discover new event opportunities

# Scoped
Analyze only the order-service/ directory for Kafka usage
Discover event candidates in the payment-service/ directory
```

### Option 2: Cursor / Windsurf / Copilot

Add the relevant skill file(s) to your project context:

**Cursor:**
- Add `skill-audit.md` and/or `skill-discover.md` to the chat context
- Prompt: `Follow the instructions in skill-audit.md to analyze this repo for Kafka`
- Or: `Follow skill-discover.md to find where Kafka events should be added`

**Windsurf:**
- Reference the skill file in Cascade chat
- Prompt: `Using skill-discover.md as your guide, scan this repo for Kafka event opportunities`

**GitHub Copilot Chat:**
- `@workspace #file:skill-audit.md Analyze this repo for Kafka applications following the phases`

### Option 3: ChatGPT / Claude.ai / Any LLM Chat

1. Copy the contents of `skill-audit.md` or `skill-discover.md` into the system prompt
2. Upload or paste your source files
3. Prompt: `Follow the phases to analyze these files`

### Option 4: Manual Audit (Human Checklist)

Use the skill files as step-by-step checklists — the grep patterns, detection tables, and templates are all human-readable.

### Option 5: CI/CD PR Gate

Use the detection patterns as automated checks in GitHub Actions or GitLab CI. See examples in `skill-audit.md` Phase 7 or the CI/CD section below.

---

## Output Structure

### Audit Mode
```
your-repo/
├── schema-report.md              # Analysis report
├── schemas/
│   ├── schema.yaml               # Schema project config
│   ├── avro/{topic}-value.avsc
│   ├── json/{topic}-value.json
│   └── proto/{topic}-value.proto
└── terraform/
    ├── providers.tf
    ├── variables.tf
    ├── tags.tf                    # confluent_tag resources
    ├── schemas.tf                 # confluent_schema resources
    ├── flagged-auto-register.tf   # Commented-out flagged resources
    ├── outputs.tf
    └── import.sh                  # Import script for existing schemas
```

### Discover Mode
```
your-repo/
├── discover-report.md             # Discovery report
└── discover/
    ├── kafka_recommendations.yaml            # Ranked candidates for human review
    ├── kafka_schemas.yaml          # Schema stubs for new events
    └── patches/
        └── {service}-kafka-producer.patch  # Git-apply-ready code patches
```

### Combined Mode
```
your-repo/
├── executive-summary.md           # Cross-references both reports
├── schema-report.md               # Audit findings
├── schemas/                       # Extracted schemas
├── terraform/                     # Terraform configs
├── discover-report.md             # Discovery findings
└── discover/
    ├── kafka_recommendations.yaml
    ├── kafka_schemas.yaml
    └── patches/
```

---

## Languages Supported

| Language | Build Files | Audit (Existing Kafka) | Discover (New Events) |
|----------|------------|----------------------|---------------------|
| Java / Kotlin / Scala | pom.xml, build.gradle | KafkaTemplate, KafkaProducer, KStream, Kafka Connect | JPA entities, Spring services, Lombok DTOs |
| Python | requirements.txt, pyproject.toml | confluent-kafka, kafka-python | Pydantic, Django models, dataclasses |
| .NET | *.csproj | Confluent.Kafka | EF Core entities, MediatR, records |
| Go | go.mod | confluent-kafka-go, sarama | Structs with json tags, GORM models |
| Node/TS | package.json | kafkajs, @confluentinc/kafka-javascript | TypeScript interfaces, Prisma, TypeORM |
| PHP | composer.json | php-rdkafka | Doctrine entities, Laravel models, Symfony |

---

## What Audit Mode Detects

### Producer Categories

| Category | What It Means | Action |
|----------|--------------|--------|
| **A: Compliant** | Uses Confluent serializer + SR | Schema extracted to Terraform |
| **B: Schema in code, no SR** | Has data models but no SR integration | Schema extracted + upgrade recommendation |
| **C: Auto-register** | `auto.register.schemas=true` | Commented-out Terraform + risk flagged |
| **D: No schema** | Raw strings/bytes | Flagged in report |
| **E: Custom serializer** | Custom Serializer impl without SR | Schema extracted + upgrade recommendation |

### PII Detection

Field names are scanned against known patterns and tagged with `confluent:tags`:

| Pattern | Tags Applied |
|---------|-------------|
| email, phone, mobile | `PII` |
| ssn, credit_card, passport | `PII`, `PRIVATE` |
| name, address, date_of_birth | `PII` |
| cpf, nino, aadhaar, sin, bsn, national_id | `PII`, `PRIVATE` |
| salary, gender, medical | `SENSITIVE` |
| password, secret, api_key | `PRIVATE` |

### Multi-Schema Topic Detection

When multiple event types flow through the same topic, Audit generates wrapper schemas with `oneOf`/union/`oneof` and `schema_reference` blocks.

### Kafka Connect / Debezium Detection

Detects Kafka Connect connectors (source and sink) by scanning for connector config files and `connector.class` references. Debezium CDC connectors are classified based on their `value.converter` setting (Category A if using AvroConverter with SR, Category C if auto-register).

### Key Schema Detection

Detects typed key serializers (`key.serializer` with Avro/JSON/Protobuf) and extracts key schemas alongside value schemas. Generates `{topic}-key` Terraform resources when the key is not a simple String.

### CI/CD Pipeline Generation

Generates a grep-based GitHub Actions workflow (`terraform/ci/schema-lint.yml`) that blocks PRs introducing `auto.register.schemas=true`, warns on `StringSerializer` for values, and warns on inline serialization patterns.

---

## What Discover Mode Finds

### Candidate Categories

| Category | What It Finds | Examples |
|----------|--------------|---------|
| DTOs/Entities | Data-carrying classes | `@Entity`, `@Data`, `BaseModel`, `record` |
| State Fields | Fields signaling events | `status`, `is_active`, `balance` |
| Service Mutations | Write-path methods | `createOrder()`, `updateStatus()`, `deleteUser()` |
| Repository Writes | Persistence operations | `save()`, `persist()`, `SaveChanges()` |
| Event Enums | Existing taxonomies | `CREATED`, `COMPLETED`, `REFUNDED` |

### Scoring & Ranking

Candidates are scored by signals (DTO=+3, state field=+2, mutation method=+3, etc.) and ranked. Top 20 are included in the plan.

### kafka_recommendations.yaml

Human-reviewable file with status tracking:

```yaml
candidates:
  - id: 1
    status: pending_review    # approve, reject, modify, or defer
    confidence: high
    service: "order-service"
    event_name: "OrderStatusChangedEvent"
    recommended_topic: "orders.order.status-changed"
    business_question: "When does an order transition states?"
    schema_fields: [...]
    downstream_consumers: [...]
```

### Code Patches

Git-apply-ready unified diffs that add Kafka producer code at identified insertion points. Patches use **Confluent serializers with Schema Registry + HeaderSchemaIdSerializer** (not raw `json.dumps` / `JSON.stringify`), include **idempotent producer config** and **error handling**, and come with the required dependency additions.

```bash
# Review the patch
cat discover/patches/order-service-kafka-producer.patch

# Apply it
git apply discover/patches/order-service-kafka-producer.patch
```

### Transactional Safety

For candidates with Risk=Medium or Risk=High, Discover recommends the **outbox pattern** instead of direct `kafkaTemplate.send()` to ensure consistency between database writes and Kafka events. Includes framework-specific guidance (Spring `@TransactionalEventListener`, Django `transaction.on_commit`, Laravel `DB::afterCommit`).

---

## Applying Discover Patches

After reviewing and approving candidates in `kafka_recommendations.yaml`:

```bash
# Apply a single patch
git apply discover/patches/order-service-kafka-producer.patch

# Apply all patches
for patch in discover/patches/*.patch; do
  git apply "$patch"
done

# Then run Audit mode on the patched repo to generate Terraform
```

---

## CI/CD Integration

Block PRs that introduce Kafka risks. Two approaches — AI-powered (full analysis) or grep-only (zero AI cost).

### Approach A: Full AI Analysis as PR Gate (GitHub Actions + Claude Code)

Runs the full Audit skill on every PR that touches Kafka files. Posts the report as a PR comment and fails the check if risks are found.

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
      - '**/composer.json'
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
          claude -p "Follow the skill-audit.md instructions to analyze this repo \
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

### Approach B: Grep-Only PR Gate (No AI, Zero Cost)

Uses the detection patterns from the skill files directly as shell grep commands. No AI tokens consumed.

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
            --include="*.go" --include="*.ts" --include="*.js" \
            --include="*.php" .; then
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
          if grep -rn "json_encode.*produce\|json_encode.*send" \
            --include="*.php" . 2>/dev/null; then
            echo "::warning::Inline json_encode in Kafka produce — use php-rdkafka with SR"
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
        - "**/composer.json"
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
        --include="*.py" --include="*.cs" --include="*.go" \
        --include="*.php" .; then
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
| Inline serialization (json.dumps, JSON.stringify, json_encode) | Warns | Warns + extracts schema from data model |
| PII field detection | Not available | Tags fields with confluent:tags |
| Schema extraction | Not available | Generates schema files |
| Terraform generation | Not available | Generates confluent_schema resources |
| Consumer impact analysis | Not available | Cross-references producers and consumers |

---

## Known Limitations

| Limitation | Applies to | Notes |
|------------|-----------|-------|
| **Patch generation is fragile** | Discover | Manually constructing unified diffs is error-prone. Use `git apply --check` to verify before applying. Expect to hand-fix some patches. |
| **Scoring heuristics are not empirically validated** | Discover | The ranking point values are reasonable defaults. Treat confidence levels as suggestions — human review is required (`pending_review`). |
| **Large repos may exhaust AI context** | Both | Repos with 1000+ files may fill the context window. Scope to specific services/directories. |
| **Framework coverage gaps** | Discover | Major frameworks covered (Spring, Django, Laravel, NestJS, EF Core). Less common frameworks (Micronaut, Quarkus, Gin, etc.) may need custom patterns. |
| **PII detection is name-based only** | Both | Fields with non-standard names containing PII will be missed. Fields matching patterns but not containing PII will be falsely tagged. Includes international identifiers (CPF, NINO, Aadhaar, etc.). Always review. |
| **Static analysis only** | Both | No runtime validation. Cannot verify events are useful at runtime. Transactional safety guidance (outbox pattern) is provided for Risk=Medium/High candidates. |
| **PHP has no native SR integration** | Both | PHP rdkafka (librdkafka) cannot use Confluent serializers natively. Patches use manual schema ID header injection. Consider REST Proxy as an alternative. |
| **Downstream consumers may be unknown** | Discover | In single-service repos, consumers can't be identified from code. Fill in during human review. |

## Prerequisites

- **Any AI coding assistant** (Claude Code, Cursor, Windsurf, Copilot) — or a human following the checklist
- **Terraform** — to apply Audit-generated configs
- **Confluent Schema Registry** — target for schema registration

## Applying the Terraform (Audit Mode)

After reviewing Audit outputs:

```bash
cd terraform

# If schemas already exist in Schema Registry, import them first:
chmod +x import.sh
export SCHEMA_REGISTRY_API_KEY=<key>
export SCHEMA_REGISTRY_API_SECRET=<secret>
export SCHEMA_REGISTRY_REST_ENDPOINT=<url>
export SCHEMA_REGISTRY_ID=<cluster-id>
./import.sh

# Initialize and apply
terraform init

export TF_VAR_schema_registry_id=lsrc-abc123
export TF_VAR_schema_registry_rest_endpoint=https://psrc-xxxxx.us-east-1.aws.confluent.cloud
export TF_VAR_schema_registry_api_key=<key>
export TF_VAR_schema_registry_api_secret=<secret>

terraform plan
terraform apply
```

Note: `confluent_tag` resources (PII, PRIVATE, SENSITIVE) are created first automatically via `depends_on`. The Terraform uses per-resource authentication (`schema_registry_cluster`, `rest_endpoint`, `credentials` blocks) compatible with Confluent provider v2.x. Import scripts require numeric schema IDs — see the generated `import.sh` for the curl command to look them up.

## Upgrade Recommendations (Audit Mode)

> **Minimum versions:** Java 8.1.1+, C/C++ 0.1.0+, Python 2.13.0+, .NET 2.13.0+, Go 2.13.0+, Node 1.8.0+.

### Category B — JSON producers without SR

Replace the serializer with the Confluent JSON serializer + header-based schema ID.
Payload stays clean JSON. Schema ID goes to Kafka headers. **Non-breaking** for consumers.
Rollout order: **producers first**, then consumers.

| Current State | Recommended |
|--------------|-------------|
| Java `StringSerializer` + JSON | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` |
| Java `JsonSerializer` (Spring) | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` |
| Python `kafka-python` + `json.dumps` | `confluent-kafka` `JSONSerializer` + `header_schema_id_serializer` |
| Python `confluent-kafka` + inline `json.dumps` | `confluent-kafka` `JSONSerializer` + `header_schema_id_serializer` |
| .NET `JsonConvert` / `System.Text.Json` | `Confluent.SchemaRegistry.Serdes.Json.JsonSerializer<T>` + header mode |
| Go `json.Marshal` | `confluent-kafka-go` JSON serializer + header mode |
| Node `kafkajs` + `JSON.stringify` | `@confluentinc/kafka-javascript` with SR + header mode |

### Category A→Header — Already on SR, migrating schema ID to headers

Add `HeaderSchemaIdSerializer` to producers. No schema extraction needed.
Confluent deserializers on supported versions automatically read schema ID from both headers and payload — **no consumer changes needed**.
Rollout order: **producers only**.

### Category E — Custom serializers (any format)

Replace the custom serializer with the appropriate Confluent serializer + `HeaderSchemaIdSerializer`.
The payload format changes, so **consumers must be upgraded first** using a composite deserializer (Java)
to handle both old and new formats during the transition.
Rollout order: **consumers first**, then producers.

| Language | Recommended |
|----------|-------------|
| Java | Replace with `KafkaAvroSerializer` / `KafkaJsonSchemaSerializer` / `ProtobufSerializer` + `HeaderSchemaIdSerializer` |
| Python (>= 2.13.0) | Replace with `confluent-kafka` serializer + `header_schema_id_serializer` |
| .NET (>= 2.13.0) | Replace with `Confluent.SchemaRegistry.Serdes` serializer + header mode |
| Go (>= 2.13.0) | Replace with `confluent-kafka-go` serializer + header mode |
| Node (>= 1.8.0) | Replace with `@confluentinc/kafka-javascript` serializer + header mode |

## Token Usage Estimates

| Repo Size | Audit | Discover | Combined |
|-----------|-------|----------|----------|
| Small (1-3 services) | 100-150K | 80-120K | 180-270K |
| Medium (5-10 services) | 200-400K | 150-300K | 350-700K |
| Large monorepo (20+) | 500K-1M | 400-800K | 900K-1.8M |

Tips to reduce token usage:
- Scope to a specific directory instead of the whole repo
- Run one mode at a time
- Two-pass: scan and report first, then generate artifacts for selected services
