# Kafka Event Discovery

Scan a backend repository to identify domain models, DTOs, entities, and service methods that are strong candidates for Kafka event publication. Produce a ranked recommendation plan, schema stubs, and ready-to-apply code patches.

## When to Use

Invoke this skill when:
- A user wants to find where Kafka events should be added in a repo
- A user asks "what should I stream?" or "where should I add Kafka producers?"
- A user wants to instrument a backend service with Kafka events
- A user wants to discover event candidates in a codebase that has little or no Kafka usage
- A user asks for a full analysis (combined with Audit mode via the orchestrator)

## Deliverables

This skill produces 4 outputs in the target repo:

1. **`discover/kafka_recommendations.yaml`** — Ranked candidates with business reasoning, for human review
2. **`discover/kafka_schemas.yaml`** — Confluent Schema Registry-compatible event schema stubs
3. **`discover/patches/`** — Git-apply-ready unified diffs that add Kafka producer code
4. **`discover-report.md`** — Full discovery report with findings and next steps

---

## Phase D0: Initialize & Scope

### D0.1 Check for Prior Audit

If Audit mode (`skill-audit.md`) already ran on this repo, read `schema-report.md` to get:
- The app catalog (services already producing/consuming Kafka)
- Topics already in use
- Schemas already extracted

Mark these services as "already instrumented." Discover should still scan them for **additional** event candidates not already being produced, but flag them differently in the output.

### D0.2 Identify Services & Modules

Find all services/modules by searching for build/dependency files:

**Glob patterns:**
```
**/pom.xml
**/build.gradle
**/build.gradle.kts
**/requirements.txt
**/pyproject.toml
**/setup.py
**/setup.cfg
**/Pipfile
**/*.csproj
**/go.mod
**/package.json
**/composer.json
```

For each build file found, determine:
- The service name (directory name or module name)
- The language (from the build file type)
- Whether it already has Kafka dependencies (check for Kafka libraries — same patterns as Audit Phase 1.1)

### D0.3 Determine Scan Scope

**Skip these directories:**
```
**/test/**
**/tests/**
**/spec/**
**/__tests__/**
**/src/test/**
**/vendor/**
**/node_modules/**
**/.git/**
**/build/**
**/dist/**
**/target/**
**/bin/**
**/obj/**
**/generated/**
**/migrations/**
**/storage/**
**/bootstrap/cache/**
```

**Scan these file types per language:**

| Language | Extensions |
|----------|-----------|
| Java | `.java` |
| Python | `.py` |
| .NET | `.cs` |
| Go | `.go` |
| Node/TS | `.ts`, `.tsx`, `.js`, `.jsx` |
| PHP | `.php` |
| Protobuf | `.proto` (cross-language schema definitions) |

---

## Phase D1: Domain Model Discovery

For each service/module, scan source files for five categories of symbols that indicate event-worthy domain concepts.

### Category 1: DTOs, Entities & Data-Carrying Classes

These are direct schema candidates — classes whose primary purpose is carrying structured data.

**Java — Grep patterns:**
```
class\s+\w+DTO\b
class\s+\w+Event\b
class\s+\w+Message\b
class\s+\w+Command\b
class\s+\w+Request\b
class\s+\w+Response\b
class\s+\w+Entity\b
class\s+\w+Model\b
record\s+\w+
@Value
@Data
@Builder
@Entity
@Document
@Table
@JsonProperty
extends SpecificRecordBase
implements Serializable
```

**Note:** Use word-boundary `\b` after class name suffixes to avoid false positives (e.g., `class ClickEventSerializer` matching `class.*Event`).

Look for:
- Lombok-annotated classes (`@Data`, `@Value`, `@Builder`, `@Getter/@Setter`)
- JPA/Hibernate entities (`@Entity`, `@Table`, `@Column`, `@Id`)
- Java Records (`public record OrderEvent(...)`)
- Spring Data MongoDB documents (`@Document`)
- Jackson-annotated classes (`@JsonProperty`, `@JsonInclude`)
- Classes in `dto/`, `model/`, `entity/`, `domain/`, `event/` packages

**Python — Grep patterns:**
```
@dataclass
class.*BaseModel
class.*TypedDict
NamedTuple
@attr.s
@attr.attrs
class.*Schema
class.*models.Model
class.*db.Model
```

Look for:
- Pydantic models (`class X(BaseModel)`)
- Dataclasses (`@dataclass`)
- Django models (`class X(models.Model)`)
- SQLAlchemy models (`class X(Base)`, `Column(`)
- Attrs classes (`@attr.s`)
- Marshmallow schemas (`class X(Schema)`)
- TypedDict definitions
- Named tuples

**.NET — Grep patterns:**
```
class.*Dto
class.*Event
class.*Message
class.*Entity
class.*Model
record\s+\w+
\[DataContract\]
\[Table\(
```

Look for:
- C# records (`public record OrderEvent`)
- EF Core entities (`DbSet<`, `[Table]`, `[Key]`, `[Column]`)
- Data contract classes (`[DataContract]`, `[DataMember]`)
- Classes in `Models/`, `Entities/`, `DTOs/`, `Events/` namespaces

**Go — Grep patterns:**
```
type\s+\w+\s+struct
json:"
```

Look for:
- Structs with `json:"field_name"` tags
- Structs in `model/`, `domain/`, `entity/` packages
- GORM models (embedding `gorm.Model`)
- Structs with `bson:`, `db:`, or `xml:` tags

**Node/TS — Grep patterns:**
```
interface\s+\w+
type\s+\w+\s*=
z\.object
class.*implements
@Entity\(\)
@Column\(\)
```

Look for:
- TypeScript interfaces and type aliases
- Zod schemas (`z.object({...})`)
- TypeORM entities (`@Entity()`, `@Column()`)
- Mongoose schemas (`new Schema({`)
- Prisma model usage (`prisma.{model}.create`)
- Class-validator decorated classes (`@IsString()`, `@IsEmail()`)

**PHP — Grep patterns:**
```
class.*DTO
class.*Event
class.*Entity
class.*Message
readonly\s+class
#\[ORM\\Entity\]
#\[ORM\\Table\]
extends\s+Model
```

Look for:
- Doctrine entities (`#[ORM\Entity]`, `#[ORM\Table]`, `#[ORM\Column]`)
- Symfony Messenger messages (`class XMessage`)
- Laravel Eloquent models (`extends Model`, `$fillable`, `$casts`)
- PHP 8.2 readonly classes (`readonly class X`)
- Laravel events (`class XEvent`)
- Value objects (classes with `readonly` properties and no setters)

**Protobuf — Grep patterns (scan `.proto` files):**
```
message\s+\w+
```

Look for:
- `message` definitions in `.proto` files — these ARE the schema
- Messages with fields named `status`, `action`, `type` — state-bearing events
- Messages in `proto/`, `protobuf/`, or `idl/` directories
- The `.proto` file is both the schema source AND the data model definition

### Category 2: State Fields (Event Signal Indicators)

Fields that track state transitions are prime candidates for event publication. Within each data class found in Category 1, look for:

**Field name patterns (case-insensitive):**

| Pattern | Why It's Valuable |
|---------|-------------------|
| `status`, `state`, `phase`, `stage` | State machine transitions are high-value events |
| `action`, `event_type`, `type` | Action/event discriminators (e.g., CREATED, UPDATED, DELETED) |
| `is_active`, `is_enabled`, `is_deleted`, `is_verified` | Boolean flags represent state changes |
| `balance`, `quantity`, `count`, `total`, `amount` | Numeric changes often trigger downstream actions |
| `updated_at`, `modified_at`, `last_changed`, `changed_at` | Mutation tracking timestamps |
| `version`, `revision` | Optimistic concurrency = tracked changes |

**Enum types signaling state:**

Look for enums referenced by state fields. Enum values that are past-tense or status-like indicate event taxonomies:

| Language | Enum Detection |
|----------|---------------|
| Java | `enum.*Status`, `enum.*State`, `enum.*Phase`, values like `CREATED`, `PENDING`, `COMPLETED`, `FAILED`, `APPROVED`, `REJECTED`, `CANCELLED` |
| Python | `class.*Enum`, `class.*IntEnum`, `class.*StrEnum`, or string constants |
| .NET | `enum.*Status`, `enum.*State` |
| Go | `const.*iota`, type aliases with string/int constants |
| Node/TS | `enum.*Status`, `enum.*State`, or union types of string literals |
| PHP | `enum.*Status`, `enum.*State` (PHP 8.1 native enums), or class constants |

### Category 3: Service Mutation Methods (Insertion Points)

These are the methods where Kafka producer calls should be inserted — the "write path."

**Java — Grep patterns:**
```
public\s+\w+\s+update
public\s+\w+\s+create
public\s+\w+\s+delete
public\s+\w+\s+save
public\s+\w+\s+process
public\s+\w+\s+handle
public\s+\w+\s+publish
public\s+\w+\s+dispatch
public\s+\w+\s+submit
public\s+\w+\s+approve
public\s+\w+\s+reject
public\s+\w+\s+cancel
public\s+\w+\s+send
public\s+\w+\s+complete
public\s+\w+\s+activate
public\s+\w+\s+deactivate
```

Note: These patterns match any return type (void, entity, DTO, etc.), not just `void`. Many service methods return the updated entity.

Also look for:
- Methods in `@Service` or `@Component` classes
- Methods annotated with `@Transactional`
- Methods that call repository save/persist operations (Category 4)
- Methods that take a DTO/entity as a parameter
- Spring `@EventListener` and `ApplicationEventPublisher.publishEvent()` — already has internal eventing, natural Kafka candidate

**Python — Grep patterns:**
```
def update_
def create_
def delete_
def save_
def send_
def process_
def handle_
def publish_
async def update_
async def create_
async def delete_
async def save_
async def send_
def perform_
def execute_
```

Also look for:
- Methods in Django views/viewsets that mutate state
- FastAPI endpoint handlers with POST/PUT/PATCH/DELETE
- Celery tasks (`@task`, `@shared_task`) — async work that could publish events

**.NET — Grep patterns:**
```
public.*async.*Task.*Update
public.*async.*Task.*Create
public.*async.*Task.*Delete
public.*async.*Task.*Save
public.*async.*Task.*Send
public.*async.*Task.*Process
public.*void\s+Update
public.*void\s+Create
public.*void\s+Save
public.*void\s+Send
```

Also look for:
- MediatR command handlers (`IRequestHandler`, `INotificationHandler`)
- Controller actions with `[HttpPost]`, `[HttpPut]`, `[HttpDelete]`
- Methods calling `SaveChangesAsync()`

**Go — Grep patterns:**
```
func.*Update
func.*Create
func.*Delete
func.*Save
func.*Send
func.*Process
func.*Handle
func.*Publish
```

Also look for:
- Exported functions (capitalized) that mutate state
- Handler functions registered on HTTP routers
- Functions that call `db.Create`, `db.Save`, `db.Update`

**Node/TS — Grep patterns:**
```
async\s+update
async\s+create
async\s+delete
async\s+save
async\s+send
async\s+process
async\s+handle
async\s+publish
```

Also look for:
- NestJS `@Injectable()` service methods
- Express/Fastify route handlers with POST/PUT/PATCH/DELETE
- Methods that call Prisma/TypeORM/Mongoose write operations

**PHP — Grep patterns:**
```
public\s+function\s+update
public\s+function\s+create
public\s+function\s+delete
public\s+function\s+save
public\s+function\s+send
public\s+function\s+store
public\s+function\s+handle
public\s+function\s+process
public\s+function\s+dispatch
public\s+function\s+publish
```

Also look for:
- Laravel controller methods (`store()`, `update()`, `destroy()`)
- Symfony command handlers
- Doctrine `EntityManager::persist()` and `flush()` calls
- Laravel event dispatching (`event()`, `Event::dispatch()`) — already has internal events

### Category 4: Repository / Persistence Write Operations

These confirm that a service method is on the write path.

| Language | Patterns |
|----------|----------|
| Java | `save(`, `persist(`, `merge(`, `saveAndFlush(`, `saveAll(`, `update(`, `delete(`, `deleteById(`, `deleteAll(` — in classes ending in `Repository`, `Dao`, `Store` |
| Python | `session.add(`, `session.commit(`, `.save(`, `.create(`, `.update(`, `.delete(`, `.objects.create(`, `.objects.update(`, `bulk_create(` |
| .NET | `SaveChanges(`, `SaveChangesAsync(`, `AddAsync(`, `Add(`, `Update(`, `Remove(`, `RemoveRange(` |
| Go | `db.Create(`, `db.Save(`, `db.Update(`, `db.Delete(`, `db.Exec(` — GORM, sqlx |
| Node/TS | `.save(`, `.create(`, `.update(`, `.delete(`, `.upsert(`, `.insertMany(`, `prisma.*.create(`, `prisma.*.update(` |
| PHP | `$em->persist(`, `$em->flush(`, `$this->entityManager->persist(`, `->save(`, `->create(`, `->update(`, `->delete(`, `DB::table(` |

### Category 5: Event Enums & Domain Event Classes

Look for existing internal event systems that could be extended to Kafka:

| Language | Patterns |
|----------|----------|
| Java | `extends ApplicationEvent`, `implements DomainEvent`, `@DomainEvents`, enums with `*Event`, `*Action`, `*Type` in name |
| Python | Django signals (`post_save`, `pre_save`), custom event classes |
| .NET | `IDomainEvent`, `INotification` (MediatR), `EventArgs` subclasses |
| Go | Channel-based event patterns, custom event structs |
| Node/TS | EventEmitter patterns, NestJS `@OnEvent()`, custom event classes |
| PHP | Laravel events (`class XEvent`), Symfony events (`class XEvent extends Event`), `#[AsEventListener]` |

---

## Phase D2: Classify & Rank Candidates

### D2.1 Scoring

Assign points to each candidate based on the signals found:

| Signal | Points | Rationale |
|--------|--------|-----------|
| Class is a DTO/VO/Event/Message (Cat 1) | +3 | Direct schema candidate |
| Class is a JPA/Doctrine/Django/EF entity | +2 | Domain model, needs change events |
| Class has state fields (Cat 2) | +2 per state field (max +8) | State transitions = high-value events. Cap at 4 fields to prevent score domination. |
| Class has PII fields | +1 | Governance benefit from SR |
| Service method is a mutation (Cat 3) | +3 | Insertion point for producer |
| Method calls a repository write (Cat 4) | +2 | Confirms write path |
| Method takes a DTO/entity as parameter | +1 | Links schema to insertion point |
| Existing internal event/listener (Cat 5) | +3 | Already eventing, natural Kafka extension |
| Class is in `domain/`, `core/`, `model/`, `entity/` package | +1 | Core domain, not infrastructure |
| Class is in `controller/`, `handler/`, `api/` package | +1 | Entry point for state changes |

### D2.2 Grouping

Group related symbols into a single candidate:
- If a service method takes a DTO as a parameter and calls a repository write, group them: the DTO is the **schema source**, the method is the **insertion point**
- If a DTO is referenced by multiple service methods, create one candidate per method (each produces a different event from the same schema)
- If an entity has internal events (`@DomainEvents`, Laravel events), group the event with its entity

### D2.3 Filtering

1. Score all candidates
2. Sort descending by score
3. Take the top 20 (or top N if the user specifies a different limit)
4. If a service already has Kafka producers (from Audit), only include candidates for events NOT already being produced

### D2.4 Confidence Levels

Based on score, assign a confidence level:

| Score | Confidence | Meaning |
|-------|------------|---------|
| 8+ | High | Strong candidate — multiple signals align |
| 5-7 | Medium | Good candidate — worth reviewing |
| 3-4 | Low | Possible candidate — needs human judgment |

---

## Phase D3: Business Reasoning

For each ranked candidate, reason about the business value. This is where the LLM's semantic understanding adds value beyond pattern matching.

### D3.1 Structured Analysis

For each candidate, produce:

```
Candidate #{N}: {EventName}
Service: {service_name}
Source: {file_path}:{line} — {ClassName}
Insertion Point: {file_path}:{line} — {methodName}()

Business Question:
  What business question does publishing this event answer?
  Example: "When does an order transition from PENDING to SHIPPED?"

Why Kafka:
  Why is this a good fit for event streaming (vs. REST, batch, polling)?
  - [specific reasons: real-time consumers, cross-service dependency,
     audit trail, analytics, event sourcing, CQRS, etc.]

Recommended Topic:
  {domain}.{entity}.{action}
  Convention: lowercase, dot-separated, past-tense verb
  Examples: orders.order.status-changed, payments.payment.completed

Downstream Consumers:
  - {service/team}: {why they would consume this}
  - If no consumers can be identified from the codebase, write:
    "Unknown — specify in kafka_recommendations.yaml after review"

Schema Complexity:
  Simple — flat fields, no nesting
  Moderate — 1-2 nested objects or arrays
  Complex — deep nesting, polymorphic types, references other schemas

Risk:
  Low — pure event emission, no transactional coupling needed
  Medium — should use outbox pattern for consistency
  High — requires saga or compensating transactions
```

### D3.2 Topic Naming Convention

Recommend topics using this convention:

```
{domain}.{entity}.{action}
```

- **domain**: the bounded context or team name (e.g., `orders`, `payments`, `users`, `inventory`)
- **entity**: the aggregate or entity name, singular (e.g., `order`, `payment`, `user`)
- **action**: past-tense verb describing what happened (e.g., `created`, `updated`, `status-changed`, `completed`, `cancelled`)

Examples:
- `orders.order.created`
- `orders.order.status-changed`
- `payments.payment.completed`
- `users.user.profile-updated`
- `inventory.product.stock-adjusted`

If the service/repo has an existing topic naming convention (detectable from Audit results or config), follow that convention instead.

**Note on dots in topic names:** Kafka converts dots to underscores in JMX metrics, so `orders.order.created` and `orders_order_created` produce identical metric bean names. This is usually acceptable but can cause metric collisions if both naming styles coexist. If this is a concern, use hyphens instead: `orders-order-created`.

### D3.3 Event Envelope Fields

Every recommended event should include these standard envelope fields:

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | string (UUID) | Unique identifier for this event instance |
| `event_type` | string | Discriminator (matches topic action, e.g., `order.created`) |
| `event_timestamp` | string (ISO-8601) | When the event occurred |
| `event_version` | string | Business-level payload format version (e.g., `"1.0"`). This is NOT the SR schema version — SR tracks versions automatically. Use this for breaking changes that require consumer logic updates. |
| `source_service` | string | Service that produced the event |

The remaining fields come from the domain model (Category 1) with PII tagging applied.

### D3.4 PII Tagging

Apply the PII detection patterns defined in `skill-audit.md` Phase 3.3b. Scan every field name in the candidate schema for potential PII and add `confluent:tags` (`PII`, `PRIVATE`, `SENSITIVE`, `PHI`) as appropriate. The full pattern table — including international identifiers (CPF, NINO, Aadhaar, etc.) — is maintained in the Audit skill to avoid duplication. Key patterns: `email`, `phone`, `ssn`, `name`, `address`, `dob`, `ip_address`, `credit_card`, `passport`, `account_number`, `salary`, `medical`.

---

## Phase D4: Generate Outputs

### D4.1 Create Output Directory

```
discover/
├── kafka_recommendations.yaml
├── kafka_schemas.yaml
└── patches/
    ├── {service}-kafka-producer.patch
    └── ...
```

### D4.2 Generate `discover/kafka_recommendations.yaml`

This is the human review document. **Nothing is auto-approved.**

```yaml
# Kafka Event Discovery Plan
# Generated by Schematizer Discover on {date}
# Repository: {repo_name}
#
# Review each candidate below. Set status to:
#   approved     — generate schema + patch
#   modified     — edit fields/topic first, then approve
#   rejected     — skip this candidate
#   deferred     — revisit later

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
    schema_format: "{JSON|AVRO|PROTOBUF}"  # See "Schema Format Selection" below
    business_question: "{one sentence — what business question does this answer?}"
    reasoning: "{why this is a good Kafka event candidate}"

    # Downstream
    downstream_consumers:
      - service: "{name}"
        reason: "{why they would consume this}"

    # Schema preview (envelope + domain fields)
    schema_fields:
      - name: "event_id"
        type: "string"
        required: true
        description: "Unique event identifier (UUID)"
      - name: "event_type"
        type: "string"
        required: true
        description: "Event type discriminator"
      - name: "event_timestamp"
        type: "string"
        format: "date-time"
        required: true
        description: "When the event occurred (ISO-8601)"
      - name: "event_version"
        type: "string"
        required: true
        description: "Schema version"
      - name: "source_service"
        type: "string"
        required: true
        description: "Service that produced the event"
      # Domain fields from the source model:
      - name: "{field_name}"
        type: "{string|integer|number|boolean|object|array}"
        required: true  # or false
        pii: false  # or true
        pii_tags: []  # e.g., ["PII", "PRIVATE"]
        description: "{field description}"

    # Assessment
    complexity: "simple"  # simple | moderate | complex
    risk: "low"  # low | medium | high
    notes: ""  # any caveats or special considerations

  # ... more candidates
```

### D4.3 Generate `discover/kafka_schemas.yaml`

Event schema stubs for all candidates. **These are planning documents, not registerable schemas.** Convert to actual JSON Schema, Avro, or Protobuf files before registering in SR (run Audit mode on the patched repo to generate registerable schemas and Terraform):

```yaml
# Kafka Event Schemas
# Generated by Schematizer Discover on {date}
# These are schema stubs — review and customize before registering.

events:
  - name: "{EventName}"
    topic: "{recommended_topic}"
    subject: "{topic}-value"
    schema_type: "{JSON|AVRO|PROTOBUF}"  # Detect from repo — see "Schema Format Selection"
    compatibility: "BACKWARD"
    source:
      service: "{service_name}"
      class: "{SourceClass}"
      file: "{relative_path}"

    fields:
      - name: "event_id"
        type: "string"
        required: true
        doc: "Unique event identifier (UUID)"
      - name: "event_type"
        type: "string"
        required: true
        doc: "Event type discriminator"
      - name: "event_timestamp"
        type: "string"
        format: "date-time"
        required: true
        doc: "ISO-8601 timestamp of when event occurred"
      - name: "event_version"
        type: "string"
        required: true
        doc: "Schema version"
      - name: "source_service"
        type: "string"
        required: true
        doc: "Service that produced the event"
      - name: "{field}"
        type: "{type}"
        required: true  # or false
        doc: "{description}"
        pii_tags: ["PII"]  # only if PII detected

    metadata:
      created_by: "schematizer-discover"
      source_model: "{ClassName}"
      reviewed: false

  # ... more events
```

### Schema Format Selection

Do **not** hardcode JSON as the schema format. Detect the appropriate format:

1. **If Audit ran first (combined mode):** Use the dominant format found in the Audit catalog. If 80%+ of existing producers use Avro, recommend Avro for new events. If mixed, match per-service.
2. **If the repo has existing schema files:** Check for `.avsc` (Avro), `.proto` (Protobuf), or `.json` (JSON Schema) files. Match the existing format.
3. **If the repo has Confluent SR dependencies:** Check the serializer libraries in build files:
   - `kafka-avro-serializer` / `kafka-streams-avro-serde` → AVRO
   - `kafka-protobuf-serializer` / `kafka-streams-protobuf-serde` → PROTOBUF
   - `kafka-json-schema-serializer` / `kafka-streams-json-schema-serde` → JSON
4. **If no signal exists:** Default to JSON (lowest barrier, no code generation needed).

Set the `schema_format` field per candidate in `kafka_recommendations.yaml` and `schema_type` in `kafka_schemas.yaml` accordingly.

### Transactional Safety

When a candidate has **Risk: Medium** or **Risk: High** (Phase D3.1), the Kafka produce should be transactionally consistent with the database write. If `kafkaTemplate.send()` or `producer.produce()` is called directly in the service method, a database rollback after a successful Kafka send creates an orphaned event.

**Outbox pattern:** Instead of producing directly, write the event to an `outbox` table in the same database transaction. A separate process (CDC connector or poller) reads the outbox and publishes to Kafka. This guarantees at-least-once delivery relative to the database (the CDC connector may re-read rows on restart). For exactly-once semantics, consumers must be idempotent.

**When to recommend the outbox pattern:**
- The service method is annotated with `@Transactional` (Java) or uses `session.commit()` (Python) or `SaveChanges()` (.NET)
- The event represents a state change that MUST be consistent with the database
- Downstream consumers take irreversible actions based on the event (e.g., sending emails, charging payments)

**When direct produce is acceptable (Risk: Low):**
- The event is observational/informational (e.g., metrics, analytics, logging)
- Consumers are idempotent and can tolerate duplicates or missed events
- The event does not represent a state transition in the source system

**Framework-specific guidance:**
- **Spring:** Use `@TransactionalEventListener(phase = AFTER_COMMIT)` to produce only after the DB transaction commits. For full outbox: use Debezium Outbox Connector.
- **Django:** Use `transaction.on_commit(lambda: producer.produce(...))` to defer until after commit.
- **Node/NestJS:** Use the `afterCommit` hook on Sequelize transactions, or implement an outbox table.
- **Laravel:** Use `DB::afterCommit(fn () => ...)` to produce after the transaction commits.
- **Go:** Use a callback after `tx.Commit()` succeeds: `if err := tx.Commit(); err == nil { producer.Produce(...) }`. For full outbox: write to an outbox table within the transaction and poll/CDC it separately.
- **.NET (EF Core):** Use `SaveChangesAsync()` with an interceptor that publishes events after commit, or subscribe to `SavingChanges`/`SavedChanges` events. For full outbox: use the Outbox pattern with a background service polling the outbox table.

For Risk=Medium/High candidates, note the transactional safety concern in `kafka_recommendations.yaml` under `notes` and recommend the appropriate pattern.

### D4.4 Generate Patch Files

For each candidate, create a git-apply-ready patch at `discover/patches/{service}-kafka-producer.patch`.

**How to construct a patch:**

1. **Read the target file.** Record exact content and line numbers.
2. **Identify insertion points:**
   - Import block (find last import, insert after)
   - Field declarations (find class body opening, insert after existing fields)
   - Constructor (find existing constructor, add parameter)
   - Method body (find the mutation method's return or closing brace, insert before)
3. **Build unified diff** manually:
   ```
   --- a/{relative_path}
   +++ b/{relative_path}
   @@ -{orig_start},{orig_count} +{new_start},{new_count} @@
    {3 lines context before}
   +{added line}
   +{added line}
    {3 lines context after}
   ```
4. **Write to** `discover/patches/{service}-kafka-producer.patch`

**Language-specific producer code to insert:**

> **Schema Registry integration:** All patches use Confluent serializers with Schema Registry
> so schemas are validated and registered. For **Java**, `HeaderSchemaIdSerializer` is fully
> configured — schema ID goes into Kafka headers, keeping payloads clean. For **Python, .NET,
> and Go**, the Confluent serializer is configured with `auto.register.schemas=false` and
> `use.latest.version=true`; adding header-based schema ID requires checking your client
> version's docs (the config property varies by language and version). For **Node/TS and PHP**,
> schema ID is manually encoded into Kafka headers since native SR serializer support varies.
>
> **Minimum client versions:** Java 8.1.1+, Python 2.13.0+, .NET 2.13.0+, Go 2.13.0+, Node 1.8.0+.

**Java (Spring Kafka + Confluent SR):**
```java
// Import
import org.springframework.kafka.core.KafkaTemplate;

// Field — use the schema-typed template, not KafkaTemplate<String, String>
private final KafkaTemplate<String, {EventClass}> kafkaTemplate;

// Constructor parameter
// Add to existing constructor: KafkaTemplate<String, {EventClass}> kafkaTemplate
// Add to constructor body: this.kafkaTemplate = kafkaTemplate;

// Add to class if no logger exists:
// private static final Logger log = LoggerFactory.getLogger({ClassName}.class);

// Producer call (at end of mutation method, before return)
try {
    kafkaTemplate.send("{topic}", {keyExpression}, {eventObject}).get(10, java.util.concurrent.TimeUnit.SECONDS);
} catch (Exception e) {
    // TODO: Add DLQ or alerting for failed produces
    log.error("Failed to produce event to {topic}", e);
    throw new RuntimeException("Kafka produce failed", e);
}
```

**Java — required Spring config (application.properties or application.yml):**
```properties
spring.kafka.producer.value-serializer=io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer
spring.kafka.producer.properties.schema.registry.url=${SCHEMA_REGISTRY_URL}
spring.kafka.producer.properties.basic.auth.credentials.source=USER_INFO
spring.kafka.producer.properties.basic.auth.user.info=${SCHEMA_REGISTRY_API_KEY}:${SCHEMA_REGISTRY_API_SECRET}
spring.kafka.producer.properties.auto.register.schemas=false
spring.kafka.producer.properties.use.latest.version=true
spring.kafka.producer.properties.value.schema.id.serializer=io.confluent.kafka.serializers.schema.id.HeaderSchemaIdSerializer
spring.kafka.producer.properties.enable.idempotence=true
spring.kafka.producer.properties.acks=all
```

**Java — required dependency (add to pom.xml or build.gradle):**
```xml
<!-- pom.xml -->
<dependency>
    <groupId>io.confluent</groupId>
    <artifactId>kafka-json-schema-serializer</artifactId>
    <version>8.2.0</version>
</dependency>
```
```groovy
// build.gradle
implementation 'io.confluent:kafka-json-schema-serializer:8.2.0'
```

**Python — required dependency (add to requirements.txt or pyproject.toml):**
```
confluent-kafka[schema-registry]>=2.13.0
```

**Python (confluent-kafka + SR):**
```python
# Import
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONSerializer
import os

# Initialization (in __init__ or module level)
sr_client = SchemaRegistryClient({
    'url': os.environ.get('SCHEMA_REGISTRY_URL', 'http://localhost:8081'),
    'basic.auth.user.info': f"{os.environ.get('SCHEMA_REGISTRY_API_KEY', '')}:{os.environ.get('SCHEMA_REGISTRY_API_SECRET', '')}"
})
# Load schema from file — adjust path to your schema location
schema_path = os.path.join(os.path.dirname(__file__), 'schemas', '{topic}-value.json')
with open(schema_path) as f:
    schema_str = f.read()
json_serializer = JSONSerializer(schema_str, sr_client, conf={'auto.register.schemas': False, 'use.latest.version': True})

self._kafka_producer = SerializingProducer({
    'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
    'value.serializer': json_serializer,
    'enable.idempotence': True,
    'acks': 'all',
})
# Note: For header-based schema ID (HeaderSchemaIdSerializer), check confluent-kafka-python >= 2.13.0
# docs for the exact configuration property. The Java equivalent is:
#   value.schema.id.serializer=io.confluent.kafka.serializers.schema.id.HeaderSchemaIdSerializer

self._delivery_error = None

def _delivery_callback(err, msg):
    if err is not None:
        self._delivery_error = err
        logger.error(f"Failed to produce to {msg.topic()}: {err}")
    else:
        logger.debug(f"Produced to {msg.topic()} [{msg.partition()}] @ {msg.offset()}")

# Producer call (after mutation logic) — pass the dict directly, not json.dumps
self._delivery_error = None
self._kafka_producer.produce(
    '{topic}',
    key=str({key_expression}),
    value={event_dict},
    on_delivery=_delivery_callback,
)
self._kafka_producer.flush()
if self._delivery_error:
    raise RuntimeError(f"Kafka produce failed: {self._delivery_error}")
```

**.NET (Confluent.Kafka + SR):**
```csharp
// Using
using Confluent.Kafka;
using Confluent.SchemaRegistry;
using Confluent.SchemaRegistry.Serdes;

// Fields
private readonly IProducer<string, {EventClass}> _producer;
private readonly ISchemaRegistryClient _srClient;

// Constructor initialization
// _srClient = new CachedSchemaRegistryClient(new SchemaRegistryConfig
// {
//     Url = Environment.GetEnvironmentVariable("SCHEMA_REGISTRY_URL"),
//     BasicAuthCredentialsSource = AuthCredentialsSource.UserInfo,
//     BasicAuthUserInfo = $"{Environment.GetEnvironmentVariable("SCHEMA_REGISTRY_API_KEY")}:{Environment.GetEnvironmentVariable("SCHEMA_REGISTRY_API_SECRET")}"
// });
// var producerConfig = new ProducerConfig
// {
//     BootstrapServers = Environment.GetEnvironmentVariable("KAFKA_BOOTSTRAP_SERVERS"),
//     EnableIdempotence = true,
//     Acks = Acks.All,
// };
// var jsonSerializerConfig = new JsonSerializerConfig
// {
//     SubjectNameStrategy = SubjectNameStrategy.Topic,
//     AutoRegisterSchemas = false,
//     UseLatestVersion = true,
// };
// // For header-based schema ID (>= 2.13.0), check the Confluent .NET docs for
// // SchemaIdLocation configuration. The Java equivalent is:
// //   value.schema.id.serializer=io.confluent.kafka.serializers.schema.id.HeaderSchemaIdSerializer
// _producer = new ProducerBuilder<string, {EventClass}>(producerConfig)
//     .SetValueSerializer(new JsonSerializer<{EventClass}>(_srClient, jsonSerializerConfig))
//     .Build();

// Producer call — pass the typed object directly
try
{
    var result = await _producer.ProduceAsync("{topic}", new Message<string, {EventClass}>
    {
        Key = {keyExpression},
        Value = {eventObject}
    });
    // TODO: Log result.Offset, result.Partition for observability
}
catch (ProduceException<string, {EventClass}> ex)
{
    // TODO: Add DLQ or alerting for failed produces
    _logger.LogError(ex, "Failed to produce event to {topic}");
    throw;
}
```

**.NET — required NuGet packages:**
```
Confluent.SchemaRegistry.Serdes.Json >= 2.13.0
```

**Go — required dependency:**
```
go get github.com/confluentinc/confluent-kafka-go/v2
```

**Go (confluent-kafka-go + SR):**
```go
// Import
import (
    "fmt"
    "github.com/confluentinc/confluent-kafka-go/v2/kafka"
    "github.com/confluentinc/confluent-kafka-go/v2/schemaregistry"
    "github.com/confluentinc/confluent-kafka-go/v2/schemaregistry/serde"
    "github.com/confluentinc/confluent-kafka-go/v2/schemaregistry/serde/jsonschema"
)

// Fields in struct
producer   *kafka.Producer
serializer *jsonschema.Serializer

// Initialization
// producer, _ := kafka.NewProducer(&kafka.ConfigMap{
//     "bootstrap.servers":   os.Getenv("KAFKA_BOOTSTRAP_SERVERS"),
//     "enable.idempotence":  true,
//     "acks":                "all",
// })
// srClient, _ := schemaregistry.NewClient(schemaregistry.NewConfigWithAuthentication(
//     os.Getenv("SCHEMA_REGISTRY_URL"),
//     os.Getenv("SCHEMA_REGISTRY_API_KEY"),
//     os.Getenv("SCHEMA_REGISTRY_API_SECRET")))
// serConfig := jsonschema.NewSerializerConfig()
// serConfig.AutoRegisterSchemas = false
// serConfig.UseLatestVersion = true
// s.serializer, _ = jsonschema.NewSerializer(srClient, serde.ValueSerde, serConfig)
// Note: For header-based schema ID, check confluent-kafka-go docs for the equivalent
// of Java's value.schema.id.serializer=HeaderSchemaIdSerializer

// Producer call — serialize via SR, not json.Marshal
payload, err := s.serializer.Serialize("{topic}", {eventStruct})
if err != nil {
    return fmt.Errorf("failed to serialize event: %w", err)
}
topic := "{topic}"
deliveryChan := make(chan kafka.Event, 1)
err = s.producer.Produce(&kafka.Message{
    TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
    Key:            []byte({keyExpression}),
    Value:          payload,
}, deliveryChan)
if err != nil {
    return fmt.Errorf("failed to enqueue message: %w", err)
}
// Wait for delivery confirmation
e := <-deliveryChan
m := e.(*kafka.Message)
if m.TopicPartition.Error != nil {
    // TODO: Add DLQ or alerting for failed produces
    return fmt.Errorf("delivery failed: %w", m.TopicPartition.Error)
}
```

**Node/TS (@confluentinc/kafka-javascript + SR):**
```typescript
// Import — use Confluent's client, not kafkajs
// Note: Verify exact package name and API against the version you install.
// The @confluentinc/kafka-javascript package API may differ by version.
import { Kafka, Producer } from '@confluentinc/kafka-javascript';

// Fields
private producer: Producer;
private schemaId: number;

// Initialization — verify exact API against the @confluentinc/kafka-javascript
// version you install. The API surface may differ from what's shown below.
// const kafka = new Kafka({
//   kafkaJS: {
//     brokers: [process.env.KAFKA_BROKERS || 'localhost:9092'],
//     clientId: '{service-name}',
//   },
// });
// this.producer = kafka.producer({
//   kafkaJS: { acks: -1 },  // acks=all
//   'enable.idempotence': true,
// });
// await this.producer.connect();
//
// // Schema ID — resolve once at startup, not per message
// // After registering via Terraform, look up the numeric ID:
// const srUrl = process.env.SCHEMA_REGISTRY_URL || 'http://localhost:8081';
// const srAuth = Buffer.from(`${process.env.SCHEMA_REGISTRY_API_KEY}:${process.env.SCHEMA_REGISTRY_API_SECRET}`).toString('base64');
// const res = await fetch(`${srUrl}/subjects/{topic}-value/versions/latest`, {
//   headers: { Authorization: `Basic ${srAuth}` },
// });
// const { id } = await res.json();
// this.schemaId = id;

// Producer call — encode schema ID into header, send clean JSON payload
const buf = Buffer.alloc(4);
buf.writeInt32BE(this.schemaId, 0);
try {
  await this.producer.send({
    topic: '{topic}',
    messages: [{
      key: String({keyExpression}),
      value: JSON.stringify({eventObject}),
      headers: { '__value_schema_id': buf },
    }],
  });
} catch (err) {
  // TODO: Add DLQ or alerting for failed produces
  console.error(`Failed to produce to {topic}:`, err);
  throw err;
}
```

**PHP (rdkafka — no native SR):**

> **Limitation:** PHP rdkafka (librdkafka) does not have native Schema Registry
> integration. There is no `KafkaJsonSchemaSerializer` equivalent for PHP.
> Options: (1) register schemas via Terraform and add the schema ID header manually,
> (2) use the Confluent REST Proxy as the producer endpoint, or (3) validate
> payloads against schemas in tests only. The patch below uses option 1.

```php
// Use
use RdKafka\Producer;
use RdKafka\Conf;

// Property
private Producer $kafkaProducer;

// Initialization (in constructor)
// $conf = new Conf();
// $conf->set('metadata.broker.list', env('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'));
// $conf->set('enable.idempotence', 'true');
// $conf->set('acks', 'all');
// $conf->setDrMsgCb(function ($kafka, $message) {
//     if ($message->err) {
//         // TODO: Add DLQ or alerting for failed produces
//         error_log("Kafka delivery failed: " . rd_kafka_err2str($message->err));
//     }
// });
// $this->kafkaProducer = new Producer($conf);

// Producer call — schema ID must be resolved after terraform apply.
// Get the numeric ID: curl -u "$SR_KEY:$SR_SECRET" "$SR_URL/subjects/{topic}-value/versions/latest" | jq '.id'
// WARNING: Do not produce with schemaId=0. Update this value before deploying.
$schemaId = (int) env('SCHEMA_ID_{TOPIC}', 0);
if ($schemaId === 0) {
    throw new \RuntimeException('Schema ID not configured — run terraform apply and set SCHEMA_ID_{TOPIC} env var');
}
$topic = $this->kafkaProducer->newTopic('{topic}');
$headers = ['__value_schema_id' => pack('N', $schemaId)];
$topic->producev(RD_KAFKA_PARTITION_UA, 0, json_encode({eventArray}), {keyExpression}, $headers);
$remaining = $this->kafkaProducer->flush(5000);
if ($remaining > 0) {
    error_log("Kafka flush incomplete: $remaining message(s) still in queue");
}
```

**Patch construction rules:**
- Include 3 lines of unchanged context before and after each hunk
- Prefix unchanged lines with a space (` `)
- Prefix added lines with `+`
- Prefix removed lines with `-` (only when modifying existing lines, e.g., constructor signature)
- Calculate `@@` line offsets correctly — account for lines added by earlier hunks
- One patch per service — if multiple files need changes, include multiple file sections in the same patch
- Add a comment header at the top of each patch file:
  ```
  # Generated by Schematizer Discover
  # Apply with: git apply discover/patches/{service}-kafka-producer.patch
  # Review kafka_recommendations.yaml and approve the candidate before applying.
  ```

**Verification instruction:** After writing each patch, read it back and verify:
- Line numbers match the original file
- Context lines match exactly (whitespace-sensitive)
- The patch has valid unified diff syntax

---

## Phase D5: Generate Report — `discover-report.md`

Create a comprehensive report at the repo root:

```markdown
# Kafka Event Discovery Report

> Generated by Schematizer Discover on {date}
> Repository: {repo_name}

---

## Executive Summary

| Metric | Count |
|--------|-------|
| Services scanned | {N} |
| Languages detected | {list} |
| Domain models found | {N} |
| Event candidates identified | {N} |
| High-confidence candidates | {N} |
| Medium-confidence candidates | {N} |
| Low-confidence candidates | {N} |
| PII fields identified | {N} |
| Services already instrumented (scanned for additional candidates) | {N} |

---

## Top Event Candidates

| # | Service | Event | Topic | Confidence | Business Value |
|---|---------|-------|-------|------------|----------------|
| 1 | {svc} | {EventName} | {topic} | High | {one-sentence summary} |
| 2 | {svc} | {EventName} | {topic} | High | {one-sentence summary} |
| ... |

---

## Detailed Candidates

### {#}. {EventName} — {ServiceName}

**Source:** `{file}:{line}` — `{ClassName}`
**Insertion Point:** `{file}:{line}` — `{methodName}()`
**Recommended Topic:** `{topic}`
**Confidence:** {High|Medium|Low} (score: {N})
**Schema Format:** {JSON|AVRO|PROTOBUF}

**Business Question:** {What business question does this event answer?}

**Why Kafka:**
- {reason 1}
- {reason 2}
- {reason 3}

**Downstream Consumers:**
- **{service/team}**: {reason}
- **{service/team}**: {reason}

**Schema Preview:**

| Field | Type | Required | PII |
|-------|------|----------|-----|
| event_id | string | Yes | |
| event_type | string | Yes | |
| event_timestamp | string (date-time) | Yes | |
| {domain_field} | {type} | {Yes/No} | {tag or —} |
| ... |

**Risk:** {Low|Medium|High} — {explanation}

---

(repeat for each candidate)

---

## Services Without Candidates

| Service | Language | Reason |
|---------|----------|--------|
| {svc} | {lang} | {No domain models found / Already fully instrumented / Infrastructure-only service} |

---

## PII Fields Detected

| # | Event | Field | Tags | Reason |
|---|-------|-------|------|--------|
| 1 | {EventName} | {field} | `PII` | Field name matches pattern: email |
| ... |

> **Total PII fields:** {N} across {M} events
>
> These fields should be tagged with `confluent:tags` when schemas are registered
> in Schema Registry. Tags enable field-level encryption, masking, and audit
> via Confluent Stream Governance.

---

## Output Files

| File | Purpose |
|------|---------|
| `discover/kafka_recommendations.yaml` | Review plan — approve, modify, or reject each candidate |
| `discover/kafka_schemas.yaml` | Schema stubs for all candidates |
| `discover/patches/*.patch` | Git-apply-ready diffs to add producer code |

---

## Next Steps

1. [ ] Review `discover/kafka_recommendations.yaml` — approve, modify, or reject each candidate
2. [ ] For approved candidates, review schema stubs in `discover/kafka_schemas.yaml`
3. [ ] Apply patches: `git apply discover/patches/{service}-kafka-producer.patch`
4. [ ] Add Kafka client dependencies to each service's build file
5. [ ] Configure Kafka connection properties (bootstrap servers, security) per environment
6. [ ] Run Schematizer Audit mode on the patched repo to generate Terraform for schema registration
7. [ ] Register schemas via `terraform apply`
8. [ ] Add schema validation to CI/CD pipeline
```

---

## Execution Notes

### How to Use This Playbook

This skill works with **any AI coding assistant or manually** — it is not tied to a specific tool.

**Claude Code (CLI):**
- Install as a skill: `cp skill-discover.md ~/.claude/skills/kafka-discover.md`
- Open Claude Code in the target repo and prompt: `Discover where Kafka events should be added in this repo`
- Claude Code uses its built-in Glob, Grep, Read, Write tools to follow the phases

**Cursor / Windsurf / Copilot:**
- Add `skill-discover.md` to the chat context
- Prompt: `Follow the instructions in skill-discover.md to discover Kafka event candidates in this repo`
- The AI will search files and follow the phases using its native capabilities

**ChatGPT / Claude.ai / Any LLM Chat:**
- Copy the contents of this file into the system prompt or first message
- Upload or paste your source files (build files, data models, service classes)
- Prompt: `Follow the phases to discover Kafka event candidates in these files`
- For large repos, focus on one service at a time

**Manual (Human Checklist):**
1. **Phase D1:** Use the grep patterns listed in each category to search your codebase
2. **Phase D2:** Score and rank matches using the heuristic table
3. **Phase D3:** For each top candidate, answer the business reasoning questions
4. **Phase D4:** Write the YAML files and patches using the templates
5. **Phase D5:** Fill in the report template

The grep patterns, scoring tables, YAML templates, and report format are all human-readable — no AI required.

### Operations Used

The phases rely on these operations, which map to tools in any AI assistant or shell commands for manual use:

| Operation | Claude Code | Cursor/Copilot | Manual (shell) |
|-----------|------------|----------------|----------------|
| Find files by pattern | `Glob` | File search | `find . -name "*.java"` |
| Search file contents | `Grep` | Content search | `grep -r "pattern" .` |
| Read a file | `Read` | Open file | `cat file` |
| Write a file | `Write` | Create file | Text editor |

### Edge Cases

- **Monorepos:** Treat each service/module with its own build file as a separate service
- **Microservices without clear boundaries:** Use directory structure as a heuristic; ask the user if unclear
- **Already-instrumented services:** If Audit data is available, only recommend events not already being produced. If Audit data is not available, scan for existing Kafka imports/usage and note overlap in the report
- **Services with internal event systems:** Treat these as HIGH-confidence candidates — the internal event is already identified as valuable, extending to Kafka is natural
- **Framework-specific patterns:** For Laravel (events, jobs, listeners), Django (signals), Spring (ApplicationEvent), NestJS (EventEmitter) — recognize these as existing event infrastructure and recommend Kafka as the cross-service transport
- **Large repos (1000+ files):** Focus on services with the richest domain models first. Use the scoring system to naturally prioritize. If the repo is too large, suggest the user specify a subset of services to scan
- **No domain models found:** If a service is purely infrastructure (API gateway, config server, etc.), skip it and note in the report
- **Generated code:** Skip files in directories named `generated/`, `gen/`, `proto_gen/`, `__generated__/`. These are outputs, not sources
- **Test code:** Skip test directories unless they contain the only model definitions (rare but possible in early-stage projects)

### Known Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Patch generation is fragile** | Manually constructing unified diffs with correct line numbers is error-prone. `git apply` will reject patches with wrong line counts or mismatched context. | Always verify patches with `git apply --check` before applying. Expect to hand-fix some patches. Patches are a starting point, not production-ready code. |
| **Scoring heuristics are untested** | The point values (DTO=+3, mutation=+3, state field=+2) are reasonable defaults but not empirically validated. Rankings may not match human judgment. | Treat confidence levels as suggestions. The `pending_review` status exists precisely because human review is required. |
| **Large repos may exhaust context** | Scanning all source files across 5 categories x 7 languages requires many grep passes. Repos with 1000+ files may fill the AI's context window before analysis completes. | Scope to specific services/directories. Run on one service at a time for large repos. |
| **Framework-specific gaps** | Patterns cover major frameworks (Spring, Django, Laravel, NestJS, EF Core) but may miss less common ones (Micronaut, Quarkus, Flask, Gin, Echo, Fiber, Slim). | The grep patterns are a starting filter — the AI should use its own judgment to identify candidates that patterns miss. Add framework-specific patterns as needed. |
| **Topic naming is opinionated** | The `{domain}.{entity}.{action}` convention may not match your organization's standards. | The plan file uses `pending_review` status. Edit topic names before approving. If an existing convention is detectable from the repo, follow it. |
| **Downstream consumer identification is limited** | In single-service repos, consumers cannot be identified from the codebase. Even in monorepos, cross-service dependencies may not be obvious from code alone. | Candidates with unknown consumers are marked as such. Fill in consumer information during human review. |
| **No runtime validation** | This tool analyzes code statically. It cannot verify that recommended events are actually useful at runtime, or that the insertion points are transactionally safe. | Use the risk assessment (Low/Medium/High) as a guide. Medium/High risk candidates should be reviewed with domain experts. |
| **PII detection is name-based** | PII tagging relies on field name patterns (email, phone, ssn). Fields with non-standard names containing PII will be missed. Fields matching patterns but not containing PII will be falsely tagged. | Always review PII tags. Add `PUBLIC` tag to false positives. Manually tag fields with non-standard names. |
| **All services in test-repo already have Kafka** | The included test-repo is designed for Audit mode — every service already has Kafka producers. There are no "greenfield" services to test Discover mode against. | When testing Discover mode, use it against a real backend repo without Kafka, or add test services without Kafka dependencies. |
