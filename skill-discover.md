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
public.*void\s+update
public.*void\s+create
public.*void\s+delete
public.*void\s+save
public.*void\s+process
public.*void\s+handle
public.*void\s+publish
public.*void\s+dispatch
public.*void\s+submit
public.*void\s+approve
public.*void\s+reject
public.*void\s+cancel
public.*void\s+send
public.*\s+complete
public.*\s+activate
public.*\s+deactivate
```

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
| Class has state fields (Cat 2) | +2 per state field | State transitions = high-value events |
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

### D3.3 Event Envelope Fields

Every recommended event should include these standard envelope fields:

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | string (UUID) | Unique identifier for this event instance |
| `event_type` | string | Discriminator (matches topic action, e.g., `order.created`) |
| `event_timestamp` | string (ISO-8601) | When the event occurred |
| `event_version` | string | Schema version (e.g., `"1.0"`) |
| `source_service` | string | Service that produced the event |

The remaining fields come from the domain model (Category 1) with PII tagging applied.

### D3.4 PII Tagging

Apply the same PII detection patterns as the Audit skill. Scan every field name in the candidate schema for potential PII:

| Pattern | Tag | Examples |
|---------|-----|---------|
| `email`, `e_mail`, `email_address`, `emailAddress` | `PII` | user_email, contact_email |
| `phone`, `phone_number`, `phoneNumber`, `mobile`, `tel` | `PII` | home_phone, mobile_number |
| `ssn`, `social_security`, `social_security_number` | `PII`, `PRIVATE` | ssn_last4 |
| `name`, `first_name`, `firstName`, `last_name`, `lastName`, `full_name` | `PII` | customer_name |
| `address`, `street`, `city`, `zip`, `zip_code`, `postal_code` | `PII` | billing_address |
| `date_of_birth`, `dateOfBirth`, `dob`, `birth_date` | `PII` | customer_dob |
| `ip`, `ip_address`, `ipAddress`, `client_ip` | `PII` | source_ip |
| `credit_card`, `creditCard`, `card_number`, `cardNumber`, `pan` | `PII`, `PRIVATE` | payment_card_number |
| `passport`, `passport_number` | `PII`, `PRIVATE` | |
| `driver_license`, `license_number` | `PII`, `PRIVATE` | |
| `account_number`, `bank_account`, `iban`, `routing_number` | `PII`, `PRIVATE` | |
| `password`, `secret`, `token`, `api_key` | `PRIVATE` | auth_token |
| `salary`, `income`, `compensation`, `wage` | `SENSITIVE` | annual_salary |
| `gender`, `sex`, `race`, `ethnicity`, `religion` | `SENSITIVE` | |
| `medical`, `diagnosis`, `prescription`, `health` | `SENSITIVE`, `PHI` | medical_record |

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
    schema_format: "JSON"
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

Confluent Schema Registry-compatible event stubs for all candidates:

```yaml
# Kafka Event Schemas
# Generated by Schematizer Discover on {date}
# These are schema stubs — review and customize before registering.

events:
  - name: "{EventName}"
    topic: "{recommended_topic}"
    subject: "{topic}-value"
    schema_type: "JSON"  # or AVRO, PROTOBUF
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

**Java (Spring Kafka):**
```java
// Import
import org.springframework.kafka.core.KafkaTemplate;

// Field
private final KafkaTemplate<String, String> kafkaTemplate;

// Constructor parameter
// Add to existing constructor: KafkaTemplate<String, String> kafkaTemplate
// Add to constructor body: this.kafkaTemplate = kafkaTemplate;

// Producer call (at end of mutation method, before return)
kafkaTemplate.send("{topic}", {keyExpression},
    objectMapper.writeValueAsString({eventObject}));
```

**Python (confluent-kafka):**
```python
# Import
from confluent_kafka import Producer
import json
import os

# Initialization (in __init__ or module level)
self._kafka_producer = Producer({
    'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
})

# Producer call (after mutation logic)
self._kafka_producer.produce(
    '{topic}',
    key=str({key_expression}),
    value=json.dumps({event_dict})
)
self._kafka_producer.flush()
```

**.NET (Confluent.Kafka):**
```csharp
// Using
using Confluent.Kafka;
using System.Text.Json;

// Field
private readonly IProducer<string, string> _producer;

// Constructor injection
// Add parameter: IProducer<string, string> producer
// Add assignment: _producer = producer;

// Producer call
await _producer.ProduceAsync("{topic}", new Message<string, string>
{
    Key = {keyExpression},
    Value = JsonSerializer.Serialize({eventObject})
});
```

**Go (confluent-kafka-go):**
```go
// Import
import (
    "encoding/json"
    "github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

// Field in struct
producer *kafka.Producer

// Producer call
eventBytes, _ := json.Marshal({eventStruct})
topic := "{topic}"
s.producer.Produce(&kafka.Message{
    TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
    Key:            []byte({keyExpression}),
    Value:          eventBytes,
}, nil)
```

**Node/TS (kafkajs):**
```typescript
// Import
import { Kafka, Producer } from 'kafkajs';

// Field
private producer: Producer;

// Initialization
// const kafka = new Kafka({ brokers: [process.env.KAFKA_BROKERS || 'localhost:9092'] });
// this.producer = kafka.producer();
// await this.producer.connect();

// Producer call
await this.producer.send({
  topic: '{topic}',
  messages: [{
    key: String({keyExpression}),
    value: JSON.stringify({eventObject}),
  }],
});
```

**PHP (rdkafka):**
```php
// Use
use RdKafka\Producer;
use RdKafka\Conf;

// Property
private Producer $kafkaProducer;

// Initialization (in constructor)
// $conf = new Conf();
// $conf->set('metadata.broker.list', env('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'));
// $this->kafkaProducer = new Producer($conf);

// Producer call
$topic = $this->kafkaProducer->newTopic('{topic}');
$topic->produce(RD_KAFKA_PARTITION_UA, 0, json_encode({eventArray}), {keyExpression});
$this->kafkaProducer->flush(1000);
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
| Services already instrumented (skipped) | {N} |

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
**Schema Format:** JSON

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
