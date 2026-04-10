# Kafka Event Discovery

Scan a backend repository to identify domain models, DTOs, entities, and service methods that are strong candidates for Kafka event publication. Produce a ranked recommendation plan, schema stubs, and ready-to-apply code patches.

## When to Use

Invoke when a user wants to find where Kafka events should be added, asks "what should I stream?", or wants to instrument a backend service with Kafka events.

## Deliverables

1. **`discover/kafka_recommendations.yaml`** — Ranked candidates with business reasoning
2. **`discover/kafka_schemas.yaml`** — SR-compatible event schema stubs
3. **`discover/patches/`** — Git-apply-ready unified diffs adding Kafka producer code
4. **`discover-report.md`** — Discovery report

---

## Phase D0: Initialize & Scope

If Audit mode (`skill-audit.md`) already ran, read `schema-report.md` for existing app catalog, topics, and schemas. Mark those services "already instrumented" but still scan for additional candidates.

Search for build/dependency files (pom.xml, build.gradle, requirements.txt, pyproject.toml, *.csproj, go.mod, package.json, composer.json, etc.). For each, determine service name, language, and existing Kafka dependencies.

Skip test/, vendor/, node_modules/, build/, target/, dist/, bin/, obj/, generated/, migrations/ directories. Scan source files matching the detected language.

---

## Phase D1: Domain Model Discovery

For each service/module, scan source files for five categories of symbols.

### Category 1: DTOs, Entities & Data-Carrying Classes

In **Java**, find classes annotated with JPA/Jackson annotations (@Entity, @Table, @Data, @Value, @Builder, @JsonProperty), records, and POJOs with getters/setters near repository or service methods. Also check for classes in dto/, model/, entity/, domain/, event/ packages. Note: `@Value` also matches Spring's property injection — verify it appears on a class declaration.

In **Python**, find Pydantic models (BaseModel), dataclasses, Django/SQLAlchemy models, attrs classes, Marshmallow schemas, TypedDicts, and NamedTuples.

In **.NET**, find C# records, EF Core entities (DbSet<>, [Table], [Key]), data contract classes, and classes in Models/, Entities/, DTOs/, Events/ namespaces.

In **Go**, find structs with json/bson/db tags, GORM models, and structs in model/, domain/, entity/ packages. Cross-reference with Cat 2/3/4 signals to filter noise.

In **Node/TS**, find TypeScript interfaces, Zod schemas, TypeORM/Mongoose entities, Prisma model usage, and class-validator decorated classes. Prioritize matches also in Cat 2/3/4.

In **PHP**, find Doctrine entities, Symfony Messenger messages, Laravel Eloquent models, PHP 8.2 readonly classes, and value objects.

In **Protobuf**, find `message` definitions — these ARE the schema. Messages with status/action/type fields are state-bearing events.

### Category 2: State Fields (Event Signal Indicators)

Within each data class from Category 1, look for fields indicating state transitions:

- **State names:** status, state, phase, stage, action, event_type, type
- **Boolean flags:** is_active, is_enabled, is_deleted, is_verified
- **Numeric changes:** balance, quantity, count, total, amount
- **Mutation timestamps:** updated_at, modified_at, last_changed, changed_at
- **Versioning:** version, revision

Find enum types referenced in entity fields that represent status/state/type. Look for values like CREATED, PENDING, COMPLETED, FAILED, APPROVED, REJECTED, CANCELLED.

### Category 3: Service Mutation Methods (Insertion Points)

Find methods that modify domain entities: create(), update(), delete(), save(), process(), handle(), publish(), dispatch(), submit(), approve(), reject(), cancel(), send(), complete(), activate(), deactivate() — and @Transactional-annotated methods.

Also look for framework-specific mutation points: Spring @EventListener, Django views with POST/PUT/DELETE, FastAPI endpoint handlers, Celery tasks, MediatR command handlers, NestJS @Injectable() services, Laravel controller store/update/destroy, Symfony command handlers.

### Category 4: Repository / Persistence Write Operations

Find persistence calls: save(), persist(), merge(), flush(), commit(), execute(), create(), update(), delete(), saveAndFlush(), SaveChanges(), SaveChangesAsync(), db.Create(), db.Save(), db.Exec(), prisma.*.create(), $em->persist(), $em->flush().

### Category 5: Event Enums & Domain Event Classes

Find existing event publishing patterns: ApplicationEvent, DomainEvent, @DomainEvents, IDomainEvent, INotification (MediatR), EventArgs, EventEmitter, .emit(), Django signals (post_save, pre_save), Laravel/Symfony event classes, Go event channels.

---

## Phase D2: Classify & Rank Candidates

### D2.1 Scoring

| Signal | Points | Rationale |
|--------|--------|-----------|
| Class is a DTO/VO/Event/Message (Cat 1) | +3 | Direct schema candidate |
| Class is a JPA/Doctrine/Django/EF entity | +2 | Domain model, needs change events |
| Class has state fields (Cat 2) | +2 per state field (max +8) | State transitions = high-value events |
| Class has PII fields | +1 | Governance benefit from SR |
| Service method is a mutation (Cat 3) | +3 | Insertion point for producer |
| Method calls a repository write (Cat 4) | +2 | Confirms write path |
| Method takes a DTO/entity as parameter | +1 | Links schema to insertion point |
| Existing internal event/listener (Cat 5) | +3 | Already eventing, natural Kafka extension |
| Class is in domain/, core/, model/, entity/ package | +1 | Core domain, not infrastructure |
| Class is in controller/, handler/, api/ package | +1 | Entry point for state changes |

### D2.2 Grouping

- If a service method takes a DTO as parameter and calls a repository write, group them: DTO = **schema source**, method = **insertion point**
- If a DTO is referenced by multiple service methods, create one candidate per method. The DTO's base score (Cat 1 + Cat 2) is shared; differentiate by method-specific signals (Cat 3 + Cat 4)
- If an entity has internal events (@DomainEvents, Laravel events), group the event with its entity

### D2.3 Filtering

1. Score all candidates
2. Sort descending by score
3. Take the top 20 (or top N if user specifies)
4. If a service already has Kafka producers (from Audit), only include events NOT already produced

### D2.4 Confidence Levels

| Score | Confidence | Meaning |
|-------|------------|---------|
| 8+ | High | Strong candidate — multiple signals align |
| 5-7 | Medium | Good candidate — worth reviewing |
| 3-4 | Low | Possible candidate — needs human judgment |
| 1-2 | — | Excluded — insufficient signals |

---

## Phase D3: Business Reasoning

### D3.1 Structured Analysis

For each candidate, produce:

```
Candidate #{N}: {EventName}
Service: {service_name}
Source: {file_path}:{line} — {ClassName}
Insertion Point: {file_path}:{line} — {methodName}()

Business Question:
  What business question does publishing this event answer?

Why Kafka:
  Why event streaming vs. REST, batch, polling?
  - [specific reasons: real-time consumers, cross-service dependency,
     audit trail, analytics, event sourcing, CQRS, etc.]

Recommended Topic:
  {domain}.{entity}.{action}

Downstream Consumers:
  - {service/team}: {why they would consume this}
  - If unknown: "Unknown — specify in kafka_recommendations.yaml after review"

Schema Complexity: Simple | Moderate | Complex

Risk:
  Low — pure event emission, no transactional coupling needed
  Medium — should use outbox pattern for consistency
  High — requires saga or compensating transactions
```

### D3.2 Topic Naming Convention

```
{domain}.{entity}.{action}
```

- **domain**: bounded context or team name (e.g., `orders`, `payments`, `users`)
- **entity**: aggregate/entity name, singular (e.g., `order`, `payment`, `user`)
- **action**: past-tense verb (e.g., `created`, `status-changed`, `completed`)

If the repo has an existing topic naming convention (from Audit or config), follow it instead.

**Note:** Kafka converts dots to underscores in JMX metrics. If metric collisions are a concern, use hyphens instead.

### D3.3 Event Envelope Fields

Every recommended event must include these standard envelope fields:

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | string (UUID) | Unique identifier for this event instance |
| `event_type` | string | Discriminator (e.g., `order.created`) |
| `event_timestamp` | string (ISO-8601) | When the event occurred |
| `event_version` | string | Business-level payload format version (NOT the SR schema version) |
| `source_service` | string | Service that produced the event |

Remaining fields come from the domain model (Cat 1) with PII tagging. If the repo already has a base event class, use that envelope structure instead and note the deviation.

### D3.4 PII Tagging

Apply PII detection from `skill-audit.md` Phase 3.3b. Tag fields with `confluent:tags` (PII, PRIVATE, SENSITIVE, PHI). Key patterns: email, phone, ssn, name, address, dob, ip_address, credit_card, passport, account_number, salary, medical (including international identifiers: CPF, NINO, Aadhaar, etc.).

---

## Phase D4: Generate Outputs

### D4.2 Generate `discover/kafka_recommendations.yaml`

This is the human review document. **Nothing is auto-approved.**

```yaml
# Kafka Event Discovery Plan
# Generated by Schematizer Discover on {date}
# Repository: {repo_name}
#
# Review each candidate. Set status to:
#   approved | modified | rejected | deferred

version: "1.0"
generated: "{ISO-8601 date}"
repository: "{repo_name}"
total_candidates: {N}
approved: 0  # updated after review

candidates:
  - id: 1
    status: pending_review
    confidence: high  # high | medium | low

    # Source
    service: "{service_directory_name}"
    language: "{Java|Python|.NET|Go|Node/TS|PHP}"
    source_file: "{relative_path_to_data_model}"
    source_class: "{ClassName}"
    source_line: {N}
    insertion_point_file: "{relative_path_to_service_method}"
    insertion_point_method: "{methodName}"
    insertion_point_line: {N}

    # Event design
    event_name: "{PascalCase}Event"
    recommended_topic: "{domain}.{entity}.{verb}"
    schema_format: "{JSON|AVRO|PROTOBUF}"
    business_question: "{one sentence}"
    reasoning: "{why this is a good Kafka event candidate}"

    # Downstream
    downstream_consumers:
      - service: "{name}"
        reason: "{why they would consume this}"

    # Schema preview: envelope fields (event_id, event_type, event_timestamp,
    # event_version, source_service) + domain fields from source model
    schema_fields:
      - name: "{field_name}"
        type: "{string|integer|number|boolean|object|array}"
        required: true
        pii: false
        pii_tags: []
        description: "{field description}"

    # Assessment
    complexity: "simple"  # simple | moderate | complex
    risk: "low"  # low | medium | high
    notes: ""
```

### D4.3 Generate `discover/kafka_schemas.yaml`

Event schema stubs for all candidates. **These are planning documents, not registerable schemas.** Convert to actual JSON Schema/Avro/Protobuf before registering (run Audit mode on the patched repo).

```yaml
# Kafka Event Schemas — stubs for review
events:
  - name: "{EventName}"
    topic: "{recommended_topic}"
    subject: "{topic}-value"
    schema_type: "{JSON|AVRO|PROTOBUF}"
    compatibility: "BACKWARD"
    source: { service: "{service_name}", class: "{SourceClass}", file: "{path}" }
    # Fields: envelope fields (event_id, event_type, event_timestamp,
    # event_version, source_service) + domain fields with pii_tags where detected
    fields:
      - { name: "{field}", type: "{type}", required: true, doc: "{desc}", pii_tags: [] }
    metadata: { created_by: "schematizer-discover", source_model: "{ClassName}", reviewed: false }
```

### Schema Format Selection

Do **not** hardcode JSON. Detect the appropriate format:

1. **If Audit ran first:** Use the dominant format from the Audit catalog. If 80%+ use Avro, recommend Avro. If mixed, match per-service.
2. **If existing schema files:** Match `.avsc` (Avro), `.proto` (Protobuf), or `.json` (JSON Schema).
3. **If SR serializer dependencies exist:** kafka-avro-serializer → AVRO, kafka-protobuf-serializer → PROTOBUF, kafka-json-schema-serializer → JSON.
4. **If no signal:** Default to JSON.

### Transactional Safety

When a candidate has **Risk: Medium or High**, the produce must be transactionally consistent with the database write.

**Outbox pattern:** Write the event to an outbox table in the same DB transaction. A CDC connector or poller publishes to Kafka. Guarantees at-least-once delivery; consumers must be idempotent for exactly-once.

**When to recommend outbox:**
- Method is @Transactional / session.commit() / SaveChanges()
- Event represents a state change that MUST be consistent with the DB
- Downstream consumers take irreversible actions (emails, payments)

**When direct produce is acceptable (Risk: Low):**
- Observational/informational events (metrics, analytics, logging)
- Consumers are idempotent and tolerate duplicates
- No state transition in the source system

**Framework-specific guidance:**
- **Spring:** `@TransactionalEventListener(phase = AFTER_COMMIT)` or Debezium Outbox Connector
- **Django:** `transaction.on_commit(lambda: producer.produce(...))`
- **Node/NestJS:** `afterCommit` hook on Sequelize transactions, or outbox table
- **Laravel:** `DB::afterCommit(fn () => ...)`
- **Go:** Callback after `tx.Commit()` succeeds, or outbox table with poll/CDC
- **.NET (EF Core):** SaveChangesAsync interceptor or SavingChanges/SavedChanges events, or outbox with background service

Note transactional safety concerns in `kafka_recommendations.yaml` under `notes`.

### D4.4 Generate Patch Files

For each candidate, create a git-apply-ready patch at `discover/patches/{service}-kafka-producer.patch`.

**Patch construction rules:**
1. Read the target file. Record exact content and line numbers.
2. Identify insertion points: import block (after last import), field declarations (after existing fields), constructor (add parameter), method body (before return or closing brace, after save() calls, within transactional boundary).
3. Build unified diff with 3 lines unchanged context before/after each hunk. Prefix unchanged=` `, added=`+`, removed=`-`. Calculate `@@` offsets correctly accounting for earlier hunks.
4. One patch per service — multiple file sections in same patch.
5. Add comment header: `# Generated by Schematizer Discover` with `git apply` instructions.
6. After writing, verify line numbers match and context lines are exact (whitespace-sensitive).

**Producer code guidance:** Generate producer code using Confluent serializers with Schema Registry. Java: KafkaTemplate + KafkaJsonSchemaSerializer + HeaderSchemaIdSerializer. Python: confluent-kafka SerializingProducer + JSONSerializer. .NET: ProducerBuilder + JsonSerializer with header mode. Go: confluent-kafka-go + jsonschema.Serializer. Node: @confluentinc/kafka-javascript. Include idempotent config (enable.idempotence=true, acks=all) and error handling stub.

**Minimum client versions for HeaderSchemaIdSerializer:** Java CP 8.0+, Python v2.10.1+, Go v2.10.1+, .NET v2.10.1+, Node v1.3.2+.

**PHP note:** PHP rdkafka has no native SR integration. Options: (1) register schemas via Terraform and add schema ID header manually, (2) use Confluent REST Proxy, or (3) validate payloads in tests only.

---

## Phase D5: Generate Report — `discover-report.md`

Report sections (use markdown tables throughout):

1. **Executive Summary** — Table with: services scanned, languages detected, domain models found, event candidates by confidence level, PII fields identified, already-instrumented services
2. **Top Event Candidates** — Table: #, Service, Event, Topic, Confidence, Business Value (one row per candidate)
3. **Detailed Candidates** — Per candidate: Source, Insertion Point, Topic, Confidence/Score, Format, Business Question, Why Kafka, Downstream Consumers, Risk, Schema Preview table (Field/Type/Required/PII)
4. **Services Without Candidates** — Table: Service, Language, Reason
5. **PII Fields Detected** — Table: Event, Field, Tags, Reason
6. **Output Files** — Table listing the 3 output files and their purpose
7. **Next Steps** — Checklist: review/approve candidates, review schemas, apply patches, add dependencies, run Audit for Terraform, register schemas

---

## Edge Cases

- **Monorepos:** Treat each service/module with its own build file as separate
- **Already-instrumented services:** Only recommend events not already produced
- **Internal event systems:** HIGH-confidence — internal events are already identified as valuable
- **Framework patterns:** Recognize Laravel events/jobs, Django signals, Spring ApplicationEvent, NestJS EventEmitter as existing event infrastructure
- **Large repos (1000+ files):** Focus on richest domain models first; suggest user scope to a subset
- **No domain models found:** Skip infrastructure-only services, note in report
- **Generated code:** Skip generated/, gen/, proto_gen/, __generated__/ directories
- **Test code:** Skip unless it contains the only model definitions

## Known Limitations

| Limitation | Mitigation |
|------------|------------|
| Patch generation is fragile | Verify with `git apply --check`. Expect hand-fixes. |
| Scoring heuristics are untested | Treat confidence as suggestions. Human review required. |
| Large repos may exhaust context | Scope to specific services. Run one service at a time. |
| Framework-specific gaps | Patterns cover major frameworks; AI should use judgment for others. |
| Topic naming is opinionated | Edit names before approving. Follow existing conventions if detectable. |
| Downstream consumer ID is limited | Mark unknown consumers; fill in during review. |
| No runtime validation | Use risk assessment as guide. Medium/High needs domain expert review. |
| PII detection is name-based | Review tags. Add PUBLIC to false positives. Manually tag non-standard names. |
| Single-pass analysis | Cross-reference Cat 3 + Cat 4 manually for indirect write paths. |
