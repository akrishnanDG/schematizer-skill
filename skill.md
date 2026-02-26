# Kafka Repo Analyzer

Scan a repository to identify Kafka applications, extract schemas, generate Terraform for Schema Registry registration, and produce a comprehensive analysis report.

## When to Use

Invoke this skill when:
- A user asks to analyze a repo for Kafka usage
- A user wants to extract schemas from Kafka producers
- A user wants Terraform to register schemas to Confluent Schema Registry
- A user wants to audit Kafka producer/consumer configurations

## Deliverables

This skill produces 3 outputs in the target repo:

1. **`schema-report.md`** — Full analysis report with findings, risks, and upgrade recommendations
2. **`schemas/`** — Extracted schema files (Avro, JSON Schema, Protobuf)
3. **`terraform/`** — Terraform configs using the Confluent provider to register schemas

---

## Phase 0: Initialize

**If `schema_status` MCP tool is available:**
```
Call schema_status with:
  path: <repo root>
```
This provides context on any existing schema project configuration (schema.yaml, registered schemas, environments). Use this to avoid duplicating work or conflicting with existing schema management.

**If MCP tools are not available:**
- Check if a `schema.yaml` file already exists in the repo
- Check if a `schemas/` directory already exists
- Note any existing schema infrastructure in the report

---

## Phase 1: Repo Scan & Kafka Detection

### 1.1 Find Build Files & Dependencies

Search the repo for build/dependency files and check for Kafka libraries.

**Glob patterns to search:**
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
**/packages.config
**/Directory.Packages.props
**/go.mod
**/package.json
```

**Dependency patterns to match:**

| Language | Dependency Strings |
|----------|-------------------|
| Java | `spring-kafka`, `kafka-clients`, `kafka-streams`, `spring-cloud-stream`, `io.confluent`, `confluent-kafka` |
| Python | `confluent-kafka`, `confluent_kafka`, `kafka-python`, `faust-streaming`, `faust` |
| .NET | `Confluent.Kafka`, `Confluent.SchemaRegistry`, `Confluent.SchemaRegistry.Serdes` |
| Go | `confluent-kafka-go`, `github.com/Shopify/sarama`, `github.com/IBM/sarama`, `github.com/segmentio/kafka-go` |
| Node/TS | `kafkajs`, `node-rdkafka`, `@confluentinc/kafka-javascript`, `kafka-node` |

### 1.2 Find Producer & Consumer Code

For each app with Kafka dependencies, search source files for producer/consumer patterns.

**Producer detection patterns (grep):**

| Language | Patterns |
|----------|----------|
| Java | `KafkaTemplate`, `KafkaProducer`, `ProducerRecord`, `@SendTo`, `StreamBridge`, `ProducerFactory`, `KStream`, `KTable`, `StreamsBuilder`, `.to(`, `.through(` |
| Python | `Producer(`, `SerializingProducer(`, `AvroProducer(`, `.produce(`, `send(topic` |
| .NET | `ProducerBuilder`, `IProducer`, `ProduceAsync`, `.Produce(` |
| Go | `kafka.NewProducer`, `sarama.NewSyncProducer`, `sarama.NewAsyncProducer`, `kafka.NewWriter` |
| Node/TS | `producer.send(`, `kafka.producer(`, `producer.produce(`, `.sendBatch(` |

**Consumer detection patterns (grep):**

| Language | Patterns |
|----------|----------|
| Java | `@KafkaListener`, `KafkaConsumer`, `ConsumerRecords`, `KafkaMessageListenerContainer`, `ConcurrentMessageListenerContainer` |
| Python | `Consumer(`, `DeserializingConsumer(`, `AvroConsumer(`, `.subscribe(`, `.poll(` |
| .NET | `ConsumerBuilder`, `IConsumer`, `.Consume(`, `ConsumerConfig` |
| Go | `kafka.NewConsumer`, `sarama.NewConsumerGroup`, `kafka.NewReader`, `.ReadMessage(` |
| Node/TS | `consumer.run(`, `kafka.consumer(`, `consumer.subscribe(`, `eachMessage` |

### 1.3 Extract Topic Names

Search for topic names in:
- String literals passed to `send()`, `produce()`, `ProducerRecord`, `@KafkaListener`, `@SendTo`
- Configuration properties: `spring.kafka.template.default-topic`, `TOPIC_NAME`, topic config constants
- YAML/properties files: `spring.kafka.consumer.topics`, `spring.kafka.producer.topic`
- Environment variables referenced for topics

### 1.4 Identify Serializers

Search for serializer configuration to determine the data format:

**Grep patterns:**
```
key.serializer
value.serializer
key.deserializer
value.deserializer
KafkaAvroSerializer
KafkaJsonSchemaSerializer
KafkaProtobufSerializer
StringSerializer
ByteArraySerializer
JsonSerializer
AvroSerializer
ProtobufSerializer
HeaderSchemaIdSerializer
schema.registry.url
SchemaRegistryClient
CachedSchemaRegistryClient
```

**Determine format from serializer:**

| Serializer Found | Schema Format | SR Integrated? |
|-----------------|---------------|----------------|
| `KafkaAvroSerializer` / `AvroSerializer` | AVRO | Yes |
| `KafkaJsonSchemaSerializer` / `JsonSchemaSerializer` | JSON | Yes |
| `KafkaProtobufSerializer` / `ProtobufSerializer` | PROTOBUF | Yes |
| `StringSerializer` + JSON data in code | JSON (infer) | No — flag for upgrade |
| `ByteArraySerializer` + Avro in code | AVRO (infer) | No — flag for upgrade |
| `JsonSerializer` (Spring default) | JSON (infer) | No — flag for upgrade |
| Custom serializer (see 1.4b) | Infer from code | No — flag for upgrade |
| No serializer / raw produce | JSON (infer) | No — flag for upgrade |

### 1.4b Detect Custom Serializers

Search the repo for classes/functions that implement serialization interfaces but do **not** use Confluent Schema Registry. These are producers serializing data themselves — bypassing SR governance entirely.

**Java — Custom serializer detection (grep):**
```
implements Serializer<
implements Serializer\b
extends Serializer<
class.*Serializer.*implements
org.apache.kafka.common.serialization.Serializer
```

Look for classes that:
- Implement `org.apache.kafka.common.serialization.Serializer<T>`
- Contain `serialize(String topic,` method
- Use `ObjectMapper`, `Gson`, `Jackson`, `org.json`, or manual JSON construction inside `serialize()`
- Use `GenericDatumWriter`, `SpecificDatumWriter`, `BinaryEncoder`, or manual Avro serialization inside `serialize()`
- Use `com.google.protobuf`, `toByteArray()`, or manual Protobuf serialization inside `serialize()`
- Do NOT reference `schema.registry.url`, `SchemaRegistryClient`, or any Confluent SR class

**Determine the data format inside the custom serializer:**
- If it uses `ObjectMapper`, `Gson`, `org.json`, `Jackson` → JSON format
- If it uses `GenericDatumWriter`, `SpecificDatumWriter`, `DatumWriter`, `BinaryEncoder`, `avro` imports → AVRO format
- If it uses `com.google.protobuf`, `toByteArray()`, `Parser`, `GeneratedMessageV3` → PROTOBUF format
- Record the format — it determines the upgrade recommendation (see Phase 4)

**Python — Custom serializer detection (grep):**
```
def serializer(
def serialize(
def value_serializer(
json.dumps.*produce
json.dumps.*send
msgpack.pack
pickle.dumps
fastavro
avro.io
DatumWriter
BinaryEncoder
```

Look for:
- Lambda or function passed as `value_serializer=` to Producer config
- Inline `json.dumps()` calls in `produce()` or `send()` arguments
- `fastavro.write` or `avro.io.DatumWriter` / `BinaryEncoder` for manual Avro serialization
- Custom functions that convert objects to bytes without SR
- Determine format: `json.dumps` → JSON, `fastavro`/`avro.io` → AVRO, `protobuf` → PROTOBUF

**.NET — Custom serializer detection (grep):**
```
ISerializer<
IAsyncSerializer<
class.*:.*ISerializer
class.*:.*IAsyncSerializer
JsonConvert.SerializeObject
System.Text.Json.JsonSerializer.Serialize
Avro.IO
Avro.Specific
Avro.Generic
Google.Protobuf
```

Look for classes implementing `ISerializer<T>` or `IAsyncSerializer<T>` that use `Newtonsoft.Json`, `System.Text.Json`, `Apache.Avro`, or `Google.Protobuf` without `SchemaRegistryClient`. Determine format from the serialization library used.

**Go — Custom serializer detection (grep):**
```
json.Marshal
json.NewEncoder
encoding/json
proto.Marshal
goavro
avro.Marshal
avro.NewCodec
```

Look for `json.Marshal()`, `proto.Marshal()`, `goavro` codec, or similar called directly before `Produce()` without SR integration. Determine format: `json.Marshal` → JSON, `goavro`/`avro` → AVRO, `proto.Marshal` → PROTOBUF.

**Node/TS — Custom serializer detection (grep):**
```
JSON.stringify.*send
JSON.stringify.*produce
Buffer.from.*JSON
serialize.*value
```

Look for `JSON.stringify()` inline in `producer.send({ value: ... })` calls.

**Classification:** Any producer using a custom serializer without SR integration is **Category E** (see Phase 4). The data model being serialized inside the custom serializer is the schema source — extract it.

### 1.5 Build App Catalog

Compile findings into a structured catalog:

```
For each Kafka application found:
  - app_name: directory or module name
  - language: Java | Python | .NET | Go | Node/TS
  - role: producer | consumer | both
  - topics: [list of topic names]
  - serializer_class: the value.serializer being used
  - custom_serializer: true | false (implements Serializer interface or inline serialization)
  - custom_serializer_file: file:line where custom serializer is defined
  - schema_format: AVRO | JSON | PROTOBUF | UNKNOWN
  - sr_integrated: true | false
  - sr_url: schema registry URL if configured
  - auto_register: true | false
  - category: A | B | C | D | E (see Phase 4)
```

---

## Phase 2: Risk Detection — `auto.register.schemas=true`

### 2.1 Scan for auto-registration

Search **all files** in the repo for auto-register patterns:

**Grep patterns (case-insensitive):**
```
auto.register.schemas\s*=\s*true
auto\.register\.schemas.*true
AutoRegisterSchemas\s*=\s*true
auto_register_schemas.*True
autoRegisterSchemas.*true
```

**Files to prioritize:**
```
**/*.properties
**/*.yml
**/*.yaml
**/application*.properties
**/application*.yml
**/*.java
**/*.py
**/*.cs
**/*.go
**/*.ts
**/*.js
**/*.json (config files)
```

### 2.2 Scan for `use.latest.version`

Also search for `use.latest.version` configuration — this is relevant for migration planning:

**Grep patterns:**
```
use.latest.version\s*=\s*true
use\.latest\.version.*true
UseLatestVersion\s*=\s*true
```

If a producer has `auto.register.schemas=true` but also `use.latest.version=true`, the migration to Terraform-managed schemas is simpler — the producer will automatically pick up the latest schema version after auto-register is disabled.

### 2.3 Record Each Occurrence

For each match, record:
- File path and line number
- The application it belongs to (from Phase 1 catalog)
- Associated topic(s)
- Whether it's in production config or test config
- Whether `use.latest.version` is also set (eases migration)

---

## Phase 3: Schema Inference

For each **producer** identified in Phase 1, extract or infer a schema.

### 3.1 Check for Existing Schema Files

Search the repo for existing schema definitions:

```
**/*.avsc          (Avro schema)
**/*.avro          (Avro schema)
**/*.proto         (Protobuf)
**/schema*.json    (JSON Schema)
**/*.schema.json   (JSON Schema)
**/schemas/**      (schema directories)
**/avro/**         (Avro directories)
```

If found, map them to the topics they serve by checking:
- File names matching topic names
- Import/reference paths in producer code
- Schema registry subject naming (`{topic}-value`, `{topic}-key`)

### 3.2 Infer from Data Models

If no schema files exist, find the data classes/models being serialized and convert them to schemas.

**Java — Find data classes:**
- Classes used as generic type in `KafkaTemplate<K, V>` or `ProducerRecord<K, V>`
- Classes with `@JsonProperty`, `@JsonInclude`, Jackson annotations
- Avro-generated classes extending `SpecificRecord`
- Protobuf-generated classes extending `GeneratedMessageV3`
- Java Records used in producer calls
- POJOs with getters/setters passed to `send()`

**Python — Find data models:**
- `@dataclass` decorated classes used in `produce()` calls
- Pydantic `BaseModel` subclasses
- `TypedDict` definitions
- Named tuples
- Dict literals passed to `produce()` — infer field types from values
- Avro schema dicts defined in code (`{"type": "record", ...}`)

**.NET — Find data models:**
- Classes/records with `[JsonProperty]`, `[DataMember]`, or `[ProtoMember]` attributes
- Types used as generic parameter in `IProducer<TKey, TValue>`
- Classes in a `Models` or `Events` namespace near producer code

**Go — Find data structs:**
- Struct types with `json:"field_name"` tags
- Struct types used in `Produce()` calls after `json.Marshal()`
- Struct types with `avro:"field_name"` tags

**TypeScript/Node — Find type definitions:**
- Interfaces or types used in `producer.send({ value: ... })`
- Zod schemas (`z.object({...})`)
- io-ts codecs
- JSON objects passed directly to send

### 3.3 Convert Data Models to Schemas

For each data model found, generate a schema file. **Tag potential PII fields** with `confluent:tags` (see 3.3b).

**To JSON Schema:**
- Map language types to JSON Schema types: `string→string`, `int/long→integer`, `float/double→number`, `boolean→boolean`, `List→array`, `Map→object`
- Include `required` array for non-nullable fields
- Add `$schema: "http://json-schema.org/draft-07/schema#"`
- Add `title` matching the class/model name
- Add `confluent:tags` to PII fields (see 3.3b)

Example with PII tags:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Customer",
  "type": "object",
  "properties": {
    "customer_id": { "type": "string" },
    "email": {
      "type": "string",
      "confluent:tags": ["PII"]
    },
    "phone_number": {
      "type": "string",
      "confluent:tags": ["PII"]
    },
    "order_total": { "type": "number" }
  },
  "required": ["customer_id", "email"]
}
```

**To Avro:**
- Use `type: "record"` with `namespace` from package/module
- Map types: `String→string`, `int→int`, `long→long`, `float→float`, `double→double`, `boolean→boolean`, `List→array`, `Map→map`
- Use `["null", "type"]` union for nullable/optional fields with `"default": null`
- Add `confluent:tags` to PII fields (see 3.3b)

Example with PII tags:
```json
{
  "type": "record",
  "name": "Customer",
  "namespace": "com.example.events",
  "fields": [
    { "name": "customer_id", "type": "string" },
    {
      "name": "email",
      "type": "string",
      "confluent:tags": ["PII"]
    },
    {
      "name": "ssn",
      "type": "string",
      "confluent:tags": ["PII", "PRIVATE"]
    },
    { "name": "order_total", "type": "double" }
  ]
}
```

**To Protobuf:**
- Use `syntax = "proto3"`
- Map types: `String→string`, `int→int32`, `long→int64`, `float→float`, `double→double`, `boolean→bool`, `List→repeated`, `Map→map<K,V>`
- Add `package` from namespace
- Add `confluent:tags` via field meta annotations (see 3.3b)

Example with PII tags:
```protobuf
syntax = "proto3";

package com.example.events;

import "confluent/meta.proto";

message Customer {
  string customer_id = 1;
  string email = 2 [(confluent.field_meta).tags = "PII"];
  string ssn = 3 [
    (confluent.field_meta).tags = "PII",
    (confluent.field_meta).tags = "PRIVATE"
  ];
  double order_total = 4;
}
```

### 3.3b Tag Potential PII Fields

When generating schemas, scan every field name for potential PII and add `confluent:tags`. This enables Confluent Stream Governance for data classification, masking, and compliance.

**PII field name patterns (case-insensitive):**

| Pattern | Tag | Examples |
|---------|-----|---------|
| `email`, `e_mail`, `email_address`, `emailAddress` | `PII` | user_email, contact_email |
| `phone`, `phone_number`, `phoneNumber`, `mobile`, `telephone`, `tel` | `PII` | home_phone, mobile_number |
| `ssn`, `social_security`, `socialSecurity`, `social_security_number` | `PII`, `PRIVATE` | ssn_last4 |
| `name`, `first_name`, `firstName`, `last_name`, `lastName`, `full_name`, `fullName` | `PII` | customer_name, user_first_name |
| `address`, `street`, `city`, `state`, `zip`, `zip_code`, `zipCode`, `postal_code`, `postalCode` | `PII` | billing_address, shipping_street |
| `date_of_birth`, `dateOfBirth`, `dob`, `birth_date`, `birthday` | `PII` | customer_dob |
| `ip`, `ip_address`, `ipAddress`, `client_ip`, `remote_addr` | `PII` | source_ip, request_ip |
| `credit_card`, `creditCard`, `card_number`, `cardNumber`, `ccn`, `pan` | `PII`, `PRIVATE` | payment_card_number |
| `passport`, `passport_number`, `passportNumber` | `PII`, `PRIVATE` | |
| `driver_license`, `driverLicense`, `license_number` | `PII`, `PRIVATE` | |
| `account_number`, `accountNumber`, `bank_account`, `iban`, `routing_number` | `PII`, `PRIVATE` | |
| `password`, `secret`, `token`, `api_key`, `apiKey` | `PRIVATE` | auth_token, access_key |
| `salary`, `income`, `compensation`, `wage` | `SENSITIVE` | annual_salary |
| `gender`, `sex`, `race`, `ethnicity`, `religion`, `nationality` | `SENSITIVE` | |
| `medical`, `diagnosis`, `prescription`, `health` | `SENSITIVE`, `PHI` | medical_record |

**Supported Confluent tag values:**

| Tag | Meaning |
|-----|---------|
| `PII` | Personally Identifiable Information — can identify an individual |
| `PRIVATE` | Highly sensitive — should be encrypted or masked |
| `SENSITIVE` | Sensitive but not directly identifying |
| `PHI` | Protected Health Information (HIPAA) |
| `PUBLIC` | Safe for broad access |

**How to apply tags:**

- **Avro:** Add `"confluent:tags": ["PII"]` as a sibling to `name` and `type` on the field
- **JSON Schema:** Add `"confluent:tags": ["PII"]` as a sibling to `type` on the property
- **Protobuf:** Add `[(confluent.field_meta).tags = "PII"]` after the field number; must import `confluent/meta.proto`

**Report PII findings:** In the report, add a PII summary table showing all tagged fields, their schemas, and the tags applied. This gives teams visibility into what PII is flowing through Kafka.

### 3.4 Infer from Sample Data

If sample data files exist (`.json`, `.ndjson`, test fixtures):

**If `schema_infer` MCP tool is available:**
```
Call schema_infer with:
  path: <path to sample data file>
  format: json (default) | avro | protobuf
  name: <schema name based on topic>
```

**If MCP tools are not available:**
- Read the sample data file
- Manually infer field names, types, required/optional from the JSON structure
- Generate a JSON Schema (draft-07) or Avro schema by hand based on the data shape
- Note in the report that schemas were inferred manually and should be reviewed

### 3.5 Validate Schemas

After extracting/generating schemas:

**If `schema_lint` MCP tool is available:**
```
Call schema_lint with:
  path: <schema file or schemas/ directory>
  fix: true
```
Fix any warnings — they prevent real problems during schema evolution.

**If MCP tools are not available:**
- Manually review each schema for:
  - Missing `default` values on optional fields (required for backward-compatible evolution)
  - Fields that may contain PII (email, phone, ssn, address, name) — add documentation
  - Naming conventions (camelCase or snake_case consistency)
  - Missing `doc` / `description` on fields
- Add a note in the report: "Schemas were not machine-validated. Run `schema_lint` before registering."

---

## Phase 4: Categorize Producers

Classify each producer into a category based on findings:

| Category | Criteria | Action |
|----------|----------|--------|
| **A: Compliant** | Uses Confluent serializer + schema.registry.url configured + no auto.register | Report as compliant. Still extract schema to Terraform if not already managed by IaC. |
| **B: Schema in code, no SR** | Has data models/classes but uses StringSerializer, JsonSerializer (Spring), kafka-python, kafkajs raw, or no Confluent SR integration | Extract schema → `terraform/schemas.tf` + add upgrade recommendation to report |
| **C: Auto-register** | Has `auto.register.schemas=true` | Extract schema → `terraform/flagged-auto-register.tf` (commented out) + flag risk in report |
| **D: No schema** | Raw strings/bytes, no discernible data model, hardcoded JSON strings | Flag in report with recommendation to adopt schema-first approach |
| **E: Custom serializer** | Implements `Serializer<T>` interface, uses `json.dumps`/`JSON.stringify`/`JsonConvert`/`json.Marshal`/`GenericDatumWriter`/`fastavro`/`proto.Marshal` inline, or has a custom serialization function — all without SR | Extract schema from the data model inside the custom serializer → `terraform/schemas.tf` + recommend replacing with the appropriate Confluent serializer based on format (see upgrade rules below) |

---

## Phase 5: Create Schema Files

### 5.1 Directory Structure

Create:
```
schemas/
├── avro/
│   ├── {topic}-value.avsc
│   └── ...
├── json/
│   ├── {topic}-value.json
│   └── ...
└── proto/
    ├── {topic}-value.proto
    └── ...
```

### 5.2 File Naming

- Value schemas: `{topic}-value.{ext}`
- Key schemas (if applicable): `{topic}-key.{ext}`
- Extensions: `.avsc` (Avro), `.json` (JSON Schema), `.proto` (Protobuf)

### 5.3 Initialize Schema Project

**If `schema_init` MCP tool is available:**
```
Call schema_init with:
  path: <repo root or schemas/ directory>
```

**If MCP tools are not available:**
- Manually create `schema.yaml` at the schemas directory root

In either case, update `schema.yaml` to include:
- All schema files under `schemas:` with `path`, `subject`, and `type`
- Schema Registry environment configuration:

```yaml
environments:
  dev:
    url: ${SCHEMA_REGISTRY_URL}
    api_key: ${SCHEMA_REGISTRY_API_KEY}
    api_secret: ${SCHEMA_REGISTRY_API_SECRET}
```

### 5.4 Lint & Validate

**If MCP tools are available:**
```
Call schema_lint with:
  path: schemas/
  fix: true

Call schema_validate with:
  path: <each schema file>
  against: main  (or live_sr if SR URL is configured)
```

**If MCP tools are not available:**
- Skip automated lint/validate
- Add to report: "⚠ Schemas were not lint-checked or compatibility-validated. Before registering, install the schema-registry MCP server and run `schema_lint` + `schema_validate`, or manually validate using the Confluent Schema Registry REST API."

---

## Phase 6: Generate Terraform

### 6.1 `terraform/providers.tf`

```hcl
terraform {
  required_version = ">= 1.3.0"

  required_providers {
    confluent = {
      source  = "confluentinc/confluent"
      version = "~> 2.0"
    }
  }
}

provider "confluent" {
  schema_registry_id            = var.schema_registry_id
  schema_registry_rest_endpoint = var.schema_registry_rest_endpoint
  schema_registry_api_key       = var.schema_registry_api_key
  schema_registry_api_secret    = var.schema_registry_api_secret
}
```

### 6.2 `terraform/variables.tf`

```hcl
variable "schema_registry_id" {
  description = "Schema Registry cluster ID (e.g., lsrc-abc123)"
  type        = string
}

variable "schema_registry_rest_endpoint" {
  description = "Schema Registry REST endpoint URL"
  type        = string
}

variable "schema_registry_api_key" {
  description = "Schema Registry API key"
  type        = string
  sensitive   = true
}

variable "schema_registry_api_secret" {
  description = "Schema Registry API secret"
  type        = string
  sensitive   = true
}
```

### 6.3 `terraform/tags.tf`

**Important:** Confluent Stream Governance requires tags to be pre-created in the catalog before schemas can embed `confluent:tags`. Generate a `confluent_tag` resource for each tag used in the schemas:

```hcl
# ──────────────────────────────────────────────
# Confluent Stream Governance Tags
# Must exist before schemas can use confluent:tags
# ──────────────────────────────────────────────

resource "confluent_tag" "pii" {
  name        = "PII"
  description = "Personally Identifiable Information — can identify an individual"
}

resource "confluent_tag" "private" {
  name        = "PRIVATE"
  description = "Highly sensitive data — should be encrypted or masked"
}

resource "confluent_tag" "sensitive" {
  name        = "SENSITIVE"
  description = "Sensitive information that requires restricted access"
}

# Add additional tags here if PHI or other custom tags are used in schemas
```

Only include tags that are actually used in the extracted schemas. Check the PII tagging results from Phase 3.3b.

### 6.4 `terraform/schemas.tf`

For each Category A, B, and E producer, generate a `confluent_schema` resource. **If any schema uses `confluent:tags`, add `depends_on` to ensure tags are created first:**

```hcl
# ──────────────────────────────────────────────
# Topic: {topic_name}
# App: {app_name} ({language})
# Source: {file_path where producer was found}
# Category: {A, B, or E}
# ──────────────────────────────────────────────
resource "confluent_schema" "{sanitized_topic_name}_value" {
  subject_name = "{topic_name}-value"
  format       = "{AVRO|JSON|PROTOBUF}"
  schema       = file("../schemas/{format_dir}/{topic_name}-value.{ext}")

  depends_on = [confluent_tag.pii, confluent_tag.private, confluent_tag.sensitive]

  lifecycle {
    prevent_destroy = true
  }
}
```

Only include tag references in `depends_on` that the schema actually uses. If a schema has no PII fields, the `depends_on` can be omitted.

**Resource naming rules:**
- Replace dots, hyphens, and special characters with underscores
- Prefix with format if multiple formats exist for same topic
- Add `_value` or `_key` suffix

**Schema references:** If a schema references another (e.g., Avro union types, Protobuf imports), add `schema_reference` blocks:

```hcl
  schema_reference {
    name         = "{referenced_type_name}"
    subject_name = "{referenced_subject}"
    version      = {version}
  }
```

### 6.5 `terraform/flagged-auto-register.tf`

For each Category C producer, generate **commented-out** resources:

```hcl
# ╔══════════════════════════════════════════════════════════════╗
# ║  FLAGGED: auto.register.schemas=true                        ║
# ║                                                              ║
# ║  The following schemas are currently auto-registered by the  ║
# ║  producer at runtime. This is a risk because:                ║
# ║  - Schema evolution is uncontrolled                          ║
# ║  - Breaking changes can be registered accidentally           ║
# ║  - No review process for schema changes                      ║
# ║                                                              ║
# ║  To fix:                                                     ║
# ║  1. Set auto.register.schemas=false in the producer config   ║
# ║  2. Uncomment the resources below                            ║
# ║  3. Run terraform apply to register schemas via IaC          ║
# ║  4. Set use.latest.version=true in the producer config       ║
# ╚══════════════════════════════════════════════════════════════╝

# ──────────────────────────────────────────────
# Topic: {topic_name}
# App: {app_name} ({language})
# auto.register.schemas=true found at: {file}:{line}
# ──────────────────────────────────────────────
# resource "confluent_schema" "{sanitized_topic_name}_value" {
#   subject_name = "{topic_name}-value"
#   format       = "{AVRO|JSON|PROTOBUF}"
#   schema       = file("../schemas/{format_dir}/{topic_name}-value.{ext}")
#
#   lifecycle {
#     prevent_destroy = true
#   }
# }
```

### 6.6 Importing Existing Schemas

If Category A or C producers already have schemas registered in Schema Registry (via auto-register or manual registration), the Terraform resources will conflict on `terraform apply`. Add import instructions to the report:

```hcl
# For schemas already registered in SR, import them before applying:
# terraform import confluent_schema.{resource_name} {sr_cluster_id}/{subject_name}/latest
#
# Required environment variables:
#   IMPORT_SCHEMA_REGISTRY_API_KEY
#   IMPORT_SCHEMA_REGISTRY_API_SECRET
#   IMPORT_SCHEMA_REGISTRY_REST_ENDPOINT
```

Add a `terraform/import.sh` helper script:

```bash
#!/bin/bash
# Import existing schemas from Schema Registry into Terraform state.
# Set these environment variables before running:
#   IMPORT_SCHEMA_REGISTRY_API_KEY
#   IMPORT_SCHEMA_REGISTRY_API_SECRET
#   IMPORT_SCHEMA_REGISTRY_REST_ENDPOINT

# {Repeat for each Category A/C schema that is already in SR}
terraform import confluent_schema.{resource_name} "{sr_cluster_id}/{subject_name}/latest"
```

### 6.7 `terraform/outputs.tf`

```hcl
# Outputs for each registered schema (uncommented resources only)
output "{sanitized_topic_name}_value_schema_id" {
  description = "Schema ID for {topic_name}-value"
  value       = confluent_schema.{sanitized_topic_name}_value.schema_identifier
}

output "{sanitized_topic_name}_value_version" {
  description = "Schema version for {topic_name}-value"
  value       = confluent_schema.{sanitized_topic_name}_value.version
}
```

---

## Phase 7: Generate Report — `schema-report.md`

Create a comprehensive markdown report at the repo root:

```markdown
# Kafka Schema Analysis Report

> Generated by Kafka Repo Analyzer on {date}
> Repository: {repo_name}

---

## Executive Summary

| Metric | Count |
|--------|-------|
| Kafka applications found | N |
| Producers | N |
| Consumers | N |
| Languages detected | Java, Python, ... |
| Topics identified | N |
| Schemas extracted | N |
| Risks found | N |
| PII fields tagged | N |
| Upgrade recommendations | N |

### Category Breakdown

| Category | Count | Description |
|----------|-------|-------------|
| A: Compliant | N | Using Confluent serializer + SR |
| B: Needs SR | N | Schema in code but no SR integration |
| C: Auto-register | N | Using auto.register.schemas=true |
| D: No schema | N | No discernible schema |
| E: Custom serializer | N | Custom Serializer/inline serialization without SR |

---

## Applications Discovered

| # | App | Language | Role | Topics | Serializer | SR? | Category |
|---|-----|----------|------|--------|------------|-----|----------|
| 1 | {app_name} | {lang} | producer | {topics} | {serializer} | {yes/no} | {A/B/C/D/E} |
| ... |

---

## RISKS

### auto.register.schemas=true

> **Impact:** Schema evolution is uncontrolled. Breaking changes can be
> registered without review, potentially breaking all downstream consumers.

| # | App | File | Line | Topics Affected |
|---|-----|------|------|----------------|
| 1 | {app} | {file} | {line} | {topics} |
| ... |

**Recommendation:**
1. Set `auto.register.schemas=false` in all producer configurations
2. Register schemas via Terraform (see `terraform/flagged-auto-register.tf`)
3. Set `use.latest.version=true` so producers fetch the latest registered schema
4. Add schema validation to CI/CD pipeline

### Custom Serializers Without Schema Registry

> **Impact:** Producers using custom serializer implementations or inline
> serialization (json.dumps, JSON.stringify, ObjectMapper, etc.) bypass
> Schema Registry entirely. Schema changes are invisible — there is no
> contract enforcement, no compatibility checking, and no schema evolution
> governance. If the data shape changes, consumers break silently.

| # | App | Custom Serializer | File:Line | Topics Affected | Data Model |
|---|-----|------------------|-----------|----------------|------------|
| 1 | {app} | {class or function name} | {file}:{line} | {topics} | {data class/model being serialized} |
| ... |

**Recommendation:**

Do NOT replace the custom serializer with a Confluent serializer — that changes the payload
format or wire encoding, which **breaks all existing consumers**.

Instead, add `HeaderSchemaIdSerializer` to inject the Schema Registry schema ID into Kafka
**headers** while keeping the custom serializer and its payload byte-identical:

1. Register the schema in Schema Registry via Terraform (already generated in `terraform/schemas.tf`)
2. Configure `HeaderSchemaIdSerializer` on the producer to write the schema ID to Kafka headers
3. Keep the existing custom serializer — the payload does not change
4. **Existing consumers will not break** — they still receive the same raw bytes
5. Schema governance is now in place: the schema is in SR, the schema ID is in message headers,
   and compatibility checks apply on future schema changes
6. See per-app upgrade instructions in the "Producer Upgrade Recommendations" section below

---

## Producer Upgrade Recommendations

For producers with schemas in code but no Schema Registry integration (Category B and E):

### {App Name} ({Language})

**Current state:**
- Serializer: `{current_serializer}`
- Data model: `{class/file path}`
- Topics: {topics}

**Recommended changes:**

1. **Add dependency:**
   {language-specific dependency to add}

2. **Update serializer config:**
   {language-specific config changes}

3. **Add Schema Registry config:**
   {language-specific SR URL and auth config}

(Repeat per app)

### Upgrade Quick Reference — JSON Data (Category B)

Replace the serializer with `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer`.
Payload stays clean JSON. Consumers don't break.

| Current State | Recommended Serializer | Config Changes |
|--------------|----------------------|----------------|
| Java `StringSerializer` + JSON | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` | Add `value.serializer`, `schema.registry.url`, `value.schema.id.serializer` |
| Java `JsonSerializer` (Spring) | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` | Add Confluent dependency, update serializer class |
| Python `kafka-python` | `confluent-kafka` `JSONSerializer` + `HeaderSchemaIdSerializer` | Replace library, use `SerializingProducer` |
| Python `confluent-kafka` + `StringSerializer` | `confluent-kafka` `JSONSerializer` + `HeaderSchemaIdSerializer` | Update serializer config |
| Python inline `json.dumps` in produce | `confluent-kafka` `JSONSerializer` + `HeaderSchemaIdSerializer` | Remove inline serialization, use `SerializingProducer` |
| .NET manual JSON (`JsonConvert`/`System.Text.Json`) | `Confluent.SchemaRegistry.Serdes.Json.JsonSerializer<T>` + `SchemaIdLocation = Header` | Add NuGet, update `ProducerBuilder` |
| Go `json.Marshal` before `Produce()` | `confluent-kafka-go` JSON Schema serializer + header mode | Remove manual marshal, add SR client |
| Node `kafkajs` raw / `JSON.stringify` | `@confluentinc/kafka-javascript` with SR schema support | Replace library, remove inline serialization, add SR config |

> **Why HeaderSchemaIdSerializer for JSON?** It puts the schema ID in Kafka headers
> and keeps the payload as clean JSON. Existing consumers parsing raw JSON continue
> to work unchanged.

### Upgrade Quick Reference — Custom Serializers (Category E)

Do NOT replace the custom serializer. Add `HeaderSchemaIdSerializer` to inject the
schema ID into Kafka headers. The custom serializer continues to produce the same
payload. Register the schema in SR via Terraform. Consumers don't break.

**Custom Avro serializers:**

| Current State | Recommendation | Config Changes |
|--------------|---------------|----------------|
| Java custom `Serializer<T>` with `GenericDatumWriter`/`SpecificDatumWriter` | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add `schema.registry.url`, `value.schema.id.serializer=HeaderSchemaIdSerializer` |
| Python `fastavro` / `avro.io.DatumWriter` without SR | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add SR client config, configure header-based schema ID |
| .NET custom `ISerializer<T>` with `Apache.Avro` | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add SR config, set `SchemaIdLocation = Header` |
| Go `goavro` / manual Avro without SR | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add SR client, configure header-based schema ID |

**Custom Protobuf serializers:**

| Current State | Recommendation | Config Changes |
|--------------|---------------|----------------|
| Java custom `Serializer<T>` with `com.google.protobuf` / `.toByteArray()` | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add `schema.registry.url`, `value.schema.id.serializer=HeaderSchemaIdSerializer` |
| Python `protobuf` / `SerializeToString()` without SR | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add SR client config, configure header-based schema ID |
| .NET custom `ISerializer<T>` with `Google.Protobuf` | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add SR config, set `SchemaIdLocation = Header` |
| Go `proto.Marshal` before `Produce()` | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add SR client, configure header-based schema ID |

**Custom JSON serializers:**

| Current State | Recommendation | Config Changes |
|--------------|---------------|----------------|
| Java custom `Serializer<T>` with Jackson/Gson | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add `schema.registry.url`, `value.schema.id.serializer=HeaderSchemaIdSerializer` |
| .NET custom `ISerializer<T>` with `Newtonsoft`/`System.Text.Json` | Keep custom serializer + add `HeaderSchemaIdSerializer` | Add SR config, set `SchemaIdLocation = Header` |

> **Why only HeaderSchemaIdSerializer for custom serializers?** Replacing the custom
> serializer with a Confluent serializer (e.g., `KafkaAvroSerializer`) changes the
> payload encoding or wire format, which breaks existing consumers. Adding only
> `HeaderSchemaIdSerializer` keeps the payload byte-identical — the schema ID goes
> into Kafka headers for governance, and consumers continue to work unchanged.

---

## Schemas Extracted

| # | Topic | Subject | Format | Source | Schema File |
|---|-------|---------|--------|--------|-------------|
| 1 | {topic} | {topic}-value | {format} | {code model / existing file / inferred} | schemas/{dir}/{file} |
| ... |

---

## PII Fields Detected

The following fields were identified as potential PII and tagged with `confluent:tags` in their schemas.
These tags enable Confluent Stream Governance features like field-level encryption, masking, and audit.

| # | Schema | Field | Tags | Reason |
|---|--------|-------|------|--------|
| 1 | {topic}-value | {field_name} | `PII` | Field name matches PII pattern: email |
| 2 | {topic}-value | {field_name} | `PII`, `PRIVATE` | Field name matches PII pattern: ssn |
| ... |

> **Total PII fields tagged:** N across M schemas
>
> **Action required:** Review tagged fields for accuracy. Add `PUBLIC` tag to
> fields that were incorrectly flagged. Add `PII`/`PRIVATE` tags to any fields
> that were missed (e.g., fields with non-standard names containing personal data).
>
> **Stream Governance:** These tags integrate with Confluent's Data Contracts
> feature. You can add `ruleset` blocks to the Terraform resources to enforce
> field-level masking or encryption on tagged fields.

---

## Terraform Resources Generated

| File | Resources | Status |
|------|-----------|--------|
| `terraform/schemas.tf` | N `confluent_schema` resources | Ready to apply |
| `terraform/flagged-auto-register.tf` | N `confluent_schema` resources | Commented out — review and enable after disabling auto-register |
| `terraform/import.sh` | N import commands | Run first if schemas already exist in SR |

---

## Consumer Impact Notes

Topics where serializer changes may affect consumers:

| Topic | Producers Changing | Active Consumers | Risk |
|-------|-------------------|-----------------|------|
| {topic} | {app changing serializer} | {consumer apps} | {impact description} |

> **Mitigation:** Using `HeaderSchemaIdSerializer` for JSON ensures backward
> compatibility. Existing consumers parsing raw JSON will not break.
> For Avro/Protobuf migrations, consumers must also be updated to use
> Confluent deserializers.

---

## Next Steps

1. [ ] Review `schema-report.md` findings with the team
2. [ ] Review and fix all `auto.register.schemas=true` occurrences
3. [ ] Review extracted schemas in `schemas/` for accuracy
4. [ ] Configure Terraform variables (SR cluster ID, endpoint, API credentials)
5. [ ] Run `terraform plan` to preview schema registration
6. [ ] Run `terraform apply` to register schemas
7. [ ] Update Category B and E producers per upgrade recommendations above
8. [ ] Remove custom serializer classes/functions after migrating to Confluent serializers
9. [ ] Uncomment `flagged-auto-register.tf` resources after disabling auto-register
10. [ ] Add schema lint/validate to CI/CD pipeline
```

---

## Execution Notes

### Tool Usage

**Core tools (always available — no prerequisites):**
- **`Glob`** — Find build files, schema files, source code
- **`Grep`** — Detect Kafka dependencies, producer/consumer patterns, serializers, risks
- **`Read`** — Read source files, data models, configs
- **`Write`** — Create schema files, Terraform configs, report

**MCP tools (optional — requires `schema-registry` MCP server):**
- **`schema_status`** — Call first to understand the repo's current schema state
- **`schema_infer`** — Generate schemas from sample JSON data files
- **`schema_lint`** — Validate all extracted schemas (always fix warnings)
- **`schema_validate`** — Check backward compatibility against main branch or live SR
- **`schema_init`** — Create `schema.yaml` project configuration

If MCP tools are not available, the skill still works — it just skips automated schema validation. The report will note which steps were skipped and recommend running them manually before registering schemas.

### Output Organization

```
{repo_root}/
├── schema-report.md              # Analysis report
├── schemas/
│   ├── schema.yaml               # Schema project config
│   ├── avro/
│   │   └── {topic}-value.avsc
│   ├── json/
│   │   └── {topic}-value.json
│   └── proto/
│       └── {topic}-value.proto
└── terraform/
    ├── providers.tf
    ├── variables.tf
    ├── tags.tf                    # confluent_tag resources (PII, PRIVATE, etc.)
    ├── schemas.tf                 # Active schema resources (depends_on tags)
    ├── flagged-auto-register.tf   # Commented-out flagged resources
    ├── outputs.tf
    └── import.sh                  # Import script for schemas already in SR
```

### Edge Cases

- **Monorepos:** Treat each service/module with its own Kafka dependencies as a separate app
- **Multi-topic producers:** Generate one schema resource per topic
- **Shared schemas:** If multiple producers use the same data model for different topics, create one schema file and reference it from multiple Terraform resources
- **No topics found:** If topic names are loaded from environment variables or external config and cannot be determined statically, note this in the report and use placeholder names with a TODO
- **Test code:** Skip test directories (`**/test/**`, `**/tests/**`, `**/__tests__/**`, `**/src/test/**`) unless they contain the only schema/model definitions
- **Multiple serializers per app:** If an app produces to multiple topics with different formats, create separate schema files and Terraform resources for each
