# Kafka Scan

Scan a repository to detect Kafka applications, classify producers into governance categories, identify risks, and output a structured app catalog. This skill does NOT generate schemas, Terraform, or reports -- use skill-audit-generate.md for artifact generation.

## When to Use

- Quick audit: detect risks, categorize producers, output catalog
- PR review: classify new/changed Kafka producers

---

## PR Mode (Incremental Scan)

Use this mode when the user says "scan this PR", "check my changes", "review this diff", or similar. It scans only changed files instead of the full repo.

### Step 1: Get Changed Files

Run `git diff --name-only main...HEAD` (substitute the actual base branch if not `main`). If on the base branch itself, use `git diff --name-only HEAD~1`.

### Step 2: Filter to Kafka-Relevant Files

From the changed files, keep only those matching:
- **Build files:** `pom.xml`, `build.gradle`, `package.json`, `go.mod`, `*.csproj`, `requirements.txt`
- **Kafka source files:** paths containing `Producer`, `Consumer`, `Serializer`, `kafka`, or `Kafka`
- **Config files:** `application.properties`, `application.yml`, `*.json` inside connector directories
- **Schema files:** `*.avsc`, `*.proto`, `*.json` inside `schemas/`

If no files match, output Status: PASS and stop.

### Step 3: Scan Matched Files Through Phases 1-4

Run the matched files through the standard Phases 1-4 logic but scoped only to those files (skip full repo discovery).

### Step 4: Check Diff for Risk Patterns

Read the actual diff (`git diff main...HEAD`) for the matched files and flag:
- `auto.register.schemas=true` added (any language variant)
- `StringSerializer`, `json.dumps`, or `JSON.stringify` added in producer code
- `kafkajs` added as a new dependency
- Schema file (`.avsc`, `.proto`) changed without a corresponding Terraform or contract update
- New Kafka producer created without `schema.registry.url` configuration

### Step 5: Output PR Review

```
## Kafka Schema Review

### Changes detected:
- {file}: {what changed}

### Risks:
- {risk description}

### Recommendations:
- {action items}

### Status: PASS / WARN / FAIL
```

**Status criteria:**
- **PASS** -- no Kafka-related risks found
- **WARN** -- Kafka changes detected but no governance violations
- **FAIL** -- `auto.register.schemas=true`, missing Schema Registry config, or wrong serializer

---

## Phase 0: Initialize

Call `schema_status` MCP tool if available (provides context on existing schema.yaml, registered schemas, environments). Otherwise, check if `schema.yaml` or `schemas/` directory already exists in the repo.

---

## Phase 1: Repo Scan & Kafka Detection

### 1.1 Find Dependencies

Search for build files (pom.xml, build.gradle, requirements.txt, pyproject.toml, *.csproj, go.mod, package.json, etc.) and check for Kafka client libraries (spring-kafka, kafka-clients, confluent-kafka, kafkajs, Confluent.Kafka, sarama, etc.).

### 1.2 Find Producers & Consumers

Search source files for producer patterns (KafkaTemplate, KafkaProducer, Producer, ProducerRecord, produce(), send(), StreamBridge, KStream) and consumer patterns (KafkaListener, KafkaConsumer, Consumer, subscribe(), poll(), eachMessage).

### 1.3 Extract Topic Names

Search for topic names in:
- String literals passed to `send()`, `produce()`, `ProducerRecord`, `@KafkaListener`, `@SendTo`
- Configuration properties: `spring.kafka.template.default-topic`, `TOPIC_NAME`, topic config constants
- YAML/properties files: `spring.kafka.consumer.topics`, `spring.kafka.producer.topic`
- Spring Cloud Stream bindings: `spring.cloud.stream.bindings.{channel}.destination`
- Environment variables referenced for topics

### 1.4 Identify Serializers

Search for serializer configuration (`key.serializer`, `value.serializer`, `schema.registry.url`, serde classes, etc.) and determine format from the serializer found:

| Serializer Found | Schema Format | SR Integrated? |
|-----------------|---------------|----------------|
| `KafkaAvroSerializer` / `AvroSerializer` | AVRO | Yes |
| `KafkaJsonSchemaSerializer` / `JsonSchemaSerializer` | JSON | Yes |
| `KafkaProtobufSerializer` / `ProtobufSerializer` | PROTOBUF | Yes |
| `SpecificAvroSerde` / `GenericAvroSerde` (Kafka Streams) | AVRO | Yes |
| `KafkaJsonSchemaSerde` (Kafka Streams) | JSON | Yes |
| `KafkaProtobufSerde` (Kafka Streams) | PROTOBUF | Yes |
| `HeaderSchemaIdSerializer` | Determined by companion serializer | Yes (SR integrated, header mode) |
| `StringSerializer` + JSON data in code | JSON (infer) | No -- flag for upgrade |
| `ByteArraySerializer` + Avro in code | AVRO (infer) | No -- flag for upgrade |
| `JsonSerializer` (Spring default) | JSON (infer) | No -- flag for upgrade |
| Custom serializer (see 1.4b) | Infer from code | No -- flag for upgrade |
| No serializer / raw produce | JSON (infer) | No -- flag for upgrade |

**Kafka Streams note:** Streams apps use Serde classes (not Serializer/Deserializer directly). The `default.value.serde` and `default.key.serde` properties determine the format. Internal topics (changelog, repartition) inherit the default serde. Do NOT generate Terraform for internal topics -- they are auto-created by Kafka Streams. Only extract schemas for source and output topics.

**REST Proxy producers:** If the repo makes HTTP POST calls to `/topics/{topic}` or uses `Content-Type: application/vnd.kafka.json.v2+json` (or similar), these are REST Proxy producers. They do not use Kafka client libraries and will not match dependency patterns in Phase 1.1. Grep for `/topics/`, `Content-Type.*vnd.kafka`, `kafka-rest`, `rest-proxy`. Classify the same way as native producers based on the HTTP body data format.

### 1.4b Detect Custom Serializers

Search for classes implementing Serializer interfaces (e.g., `implements Serializer<T>`, `ISerializer<T>`) or inline serialization (json.dumps, JSON.stringify, json.Marshal, ObjectMapper, etc.) without Schema Registry. Classify as **Category E**.

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

### 1.6 Detect Multi-Schema Topics

After building the app catalog, check if multiple data models produce to the same topic:

1. Group all producers by topic name from the catalog
2. For each topic, check if there are multiple producers with **different** data models
3. Same data model to same topic = normal (dedup the schema)
4. Different data models to same topic = **multi-schema topic** -- flag for special handling (wrapper schemas and per-type subject registration are handled by the generate skill)

### 1.7 Detect Kafka Connect Connectors

Search for connector config files (`**/connect*.properties`, `**/connect*.json`, `**/*connector*.json`, `**/*connector*.yml`, `**/connectors/**`) and grep for `connector.class`, `io.debezium`, `io.confluent.connect`, converter classes.

**Classification -- C-App vs C-Connector:**

This distinction is critical. `auto.register.schemas=true` means completely different things depending on where it appears:

| Context | Meaning | Classification |
|---------|---------|----------------|
| Application producer config (Spring Boot properties, Python `ProducerConfig`, .NET `ProducerConfig`, Go `ConfigMap`) | Developer left the default on or didn't know the risk. SR schema evolves silently. Breaking. | **Category C (Application)** -- flag as risk, disable immediately |
| Kafka Connect source connector converter config (`key.converter.auto.register.schemas`, `value.converter.auto.register.schemas`) | Connector introspects the source system schema at runtime and must register it. This is by design for source connectors and cannot be disabled without breaking the connector. | **Category C (Connector)** -- expected behavior, apply connector governance instead |

**Connector types that require auto-register by design (do NOT flag as misconfiguration):**

| Connector Family | Examples | Why auto-register is required |
|-----------------|----------|-------------------------------|
| CDC connectors | Debezium PostgreSQL, MySQL, SQL Server, Oracle, MongoDB; Confluent JDBC Source | Introspects source table DDL at runtime. Schema is determined by the source DB, not by developer code. Disabling auto-register breaks the connector. |
| File/object source | Confluent S3 Source, GCS Source, Azure Blob Source | Reads schema from file headers or infers from data shape. |
| NoSQL source | MongoDB Atlas Source, DynamoDB Source, Cassandra Source | Source schema is dynamic and schema-inferred at runtime. |
| Replication connectors | MirrorMaker2 (MM2) with SR replication | Mirrors schemas from another SR cluster. Registering them manually would duplicate or conflict. |
| SaaS source connectors | Salesforce Source, ServiceNow Source, Zendesk Source | SaaS schema is owned by the vendor and changes outside developer control. |

**For Category C (Connector) -- 5 governance actions (NOT disabling auto-register):**

1. **Compatibility mode** -- Set compatibility mode explicitly per subject via `confluent_subject_config` in Terraform. For CDC connectors, `NONE` or `BACKWARD` is typical since source DDL changes may not be fully backward-compatible. Document the choice.

2. **Subject naming strategy** -- Configure `value.converter.schema.registry.subject.naming.strategy`:
   - `TopicNameStrategy` (default): `{topic}-value`
   - `RecordNameStrategy`: `{namespace}.{RecordName}`
   - `TopicRecordNameStrategy`: `{topic}-{RecordName}` -- **recommended for CDC** so each table's schema is independently versioned.

3. **PII tagging** -- Source connectors register schemas with no `confluent:tags` (schema is generated from DB column metadata). Apply PII tags post-registration via Terraform `confluent_tag_binding` resources, Stream Catalog UI/API, or SMTs (MaskField, ReplaceField) for masking before data lands in Kafka.

4. **Schema monitoring** -- Enable alerting when a connector registers an unexpected new subject or schema version (indicates source DDL changed). Use SR webhooks or poll `GET /subjects/{subject}/versions`.

5. **Terraform import** -- After the connector has registered schemas, import them into Terraform state:
   ```bash
   terraform import confluent_schema.{resource_name} "$SCHEMA_REGISTRY_ID/{subject_name}/latest"
   ```

**For Category C (Application) -- standard remediation:**
1. Set `auto.register.schemas=false` in the producer config
2. Register schemas via Terraform
3. Set `use.latest.version=true` so the producer fetches the latest registered schema version

Add discovered connectors to the app catalog with `role: connector-source` or `role: connector-sink`. Record the connector family (CDC, file, SaaS, replication) to select the correct governance path.

### 1.8 Detect Key Schemas

Check `key.serializer` config for each producer. If it uses a Confluent SR serializer (KafkaAvroSerializer, KafkaJsonSchemaSerializer, KafkaProtobufSerializer), extract the key data model. If it uses StringSerializer, LongSerializer, IntegerSerializer, or ByteArraySerializer, no key schema is needed. For each topic with a typed key, record `{topic}-key` as an additional schema subject.

---

## Phase 2: Risk Detection

Search **all files** for `auto.register.schemas=true` (and language-specific variants like `AutoRegisterSchemas`, `auto_register_schemas`) and `use.latest.version=true`. For each match, record: file path, line number, the app it belongs to (from Phase 1 catalog), associated topics, whether it is production or test config, and whether `use.latest.version` is also set (eases migration).

---

## Phase 3: Schema & PII Discovery

### 3.1 Find Existing Schema Files

Search the repo for `**/*.avsc`, `**/*.proto`, `**/schema*.json`, `**/*.schema.json`, `**/schemas/**`, `**/avro/**`. Map them to topics by checking file names, import paths in producer code, and SR subject naming conventions.

### 3.2 Find Data Models

For each producer, find the data classes/models being serialized (generic type parameters, annotated classes, dataclasses, structs, interfaces). If no typed model exists, look for inline data construction (dicts, maps, JSON tree APIs, builders, ORM entities) and infer fields from keys/properties.

### 3.3 PII Field Detection

When analyzing schemas or data models, scan every field name for potential PII:

**PII field name patterns (case-insensitive):**

| Pattern | Tag | Examples |
|---------|-----|---------|
| `email`, `e_mail`, `email_address`, `emailAddress` | `PII` | user_email, contact_email |
| `phone`, `phone_number`, `phoneNumber`, `mobile`, `telephone`, `tel` | `PII` | home_phone, mobile_number |
| `ssn`, `social_security`, `socialSecurity`, `social_security_number` | `PII`, `PRIVATE` | ssn_last4 |
| `first_name`, `firstName`, `last_name`, `lastName`, `full_name`, `fullName`, `customer_name`, `user_name`, `person_name`, `display_name` | `PII` | Note: bare `name` has high false-positive rate. Only match when prefixed with person-related terms. |
| `address`, `street`, `city`, `state`, `zip`, `zip_code`, `zipCode`, `postal_code`, `postalCode` | `PII` | billing_address, shipping_street |
| `date_of_birth`, `dateOfBirth`, `dob`, `birth_date`, `birthday` | `PII` | customer_dob |
| `ip`, `ip_address`, `ipAddress`, `client_ip`, `remote_addr` | `PII` | source_ip, request_ip |
| `credit_card`, `creditCard`, `card_number`, `cardNumber`, `ccn`, `pan` | `PII`, `PRIVATE` | payment_card_number |
| `passport`, `passport_number`, `passportNumber` | `PII`, `PRIVATE` | |
| `driver_license`, `driverLicense`, `license_number` | `PII`, `PRIVATE` | |
| `cpf`, `cnpj` (Brazil), `nino` (UK), `aadhaar` (India), `sin` (Canada), `bsn` (Netherlands), `curp` (Mexico), `national_id`, `govt_id`, `tax_id` | `PII`, `PRIVATE` | international identifiers |
| `account_number`, `accountNumber`, `bank_account`, `iban`, `routing_number` | `PII`, `PRIVATE` | |
| `password`, `secret`, `token`, `api_key`, `apiKey` | `PRIVATE` | auth_token, access_key |
| `salary`, `income`, `compensation`, `wage` | `SENSITIVE` | annual_salary |
| `gender`, `sex`, `race`, `ethnicity`, `religion`, `nationality` | `SENSITIVE` | |
| `medical`, `diagnosis`, `prescription`, `health` | `SENSITIVE`, `PHI` | medical_record |

**Supported Confluent tag values:**

| Tag | Meaning |
|-----|---------|
| `PII` | Personally Identifiable Information -- can identify an individual |
| `PRIVATE` | Highly sensitive -- should be encrypted or masked |
| `SENSITIVE` | Sensitive but not directly identifying |
| `PHI` | Protected Health Information (HIPAA) |
| `PUBLIC` | Safe for broad access |

### Schema Format Selection

When determining the schema format for each producer:

1. **If the producer already uses a Confluent SR serializer** -- match its format (Avro/JSON/Protobuf)
2. **If existing schema files exist in the repo** (`.avsc`, `.proto`, `.schema.json`) -- match that format
3. **If the producer uses a non-SR serializer** (Category B/E) -- use the format of the data being serialized: ObjectMapper/json.dumps/JSON.stringify/json_encode = JSON Schema; GenericDatumWriter/fastavro/avro.io = Avro; proto.Marshal/toByteArray()/GeneratedMessageV3 = Protobuf
4. **If no signal exists** -- default to JSON Schema

---

## Phase 4: Categorize Producers

Classify each producer based on findings:

| Category | Criteria | Action |
|----------|----------|--------|
| **A: Compliant** | Uses Confluent serializer + schema.registry.url configured + `auto.register.schemas` is explicitly `false` or absent on client versions where the default is `false` (Java >= 7.x, Python >= 2.0) | Report as compliant. Still extract schema to Terraform if not already managed by IaC. If Terraform files already exist in the repo for these subjects, skip generation. |
| **A->Header: Already on SR, migrating to headers** | Uses Confluent serializer + SR, wants to move schema ID from payload prefix to Kafka headers | No schema extraction needed. Add `HeaderSchemaIdSerializer` to producers. Consumers need no changes -- Confluent deserializers on supported versions automatically check both headers and payload for schema ID. |
| **B: Schema in code, no SR** | Has data models/classes but uses StringSerializer, JsonSerializer (Spring), kafka-python, kafkajs raw, or no Confluent SR integration | Extract schema, recommend SR upgrade |
| **C-App: Auto-register (application)** | Application producer has `auto.register.schemas=true` in its own config (Spring Boot properties, Python ProducerConfig, .NET ProducerConfig, Go ConfigMap) | Flag as risk. Remediation: disable auto-register, register via Terraform, set `use.latest.version=true`. |
| **C-Connector: Auto-register (connector-native)** | Kafka Connect source connector uses `auto.register.schemas=true` in converter config -- CDC, JDBC Source, S3 Source, SaaS source, MirrorMaker2, etc. | Expected behavior -- do NOT disable. Apply connector governance: compatibility mode, subject naming strategy, PII tagging, schema monitoring, Terraform import. |
| **D: No schema** | Raw strings/bytes where field names and types cannot be reliably determined (e.g., raw CSV without headers, binary protocols, obfuscated data). If inline JSON keys are visible and a schema can be inferred, classify as Category B instead. | Flag with recommendation to adopt schema-first approach |
| **E: Custom serializer** | Implements `Serializer<T>` interface, uses json.dumps/JSON.stringify/JsonConvert/json.Marshal/GenericDatumWriter/fastavro/proto.Marshal inline, or has a custom serialization function -- all without SR | Extract schema from the data model inside the custom serializer, recommend replacing with Confluent serializer + `HeaderSchemaIdSerializer`. Consumers must be upgraded first. |

---

## Output

The app catalog is the primary output. It serves as input to skill-audit-generate.md for schema extraction, Terraform generation, and report creation.
