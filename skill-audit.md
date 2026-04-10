# Kafka Audit

Scan a repository to identify existing Kafka applications, extract schemas, generate Terraform for Schema Registry registration, and produce a comprehensive analysis report.

## When to Use

Invoke this skill when:
- A user asks to analyze or audit a repo for Kafka usage
- A user wants to extract schemas from Kafka producers
- A user wants Terraform to register schemas to Confluent Schema Registry
- A user wants to audit Kafka producer/consumer configurations
- A user asks for a full analysis (combined with Discover mode via the orchestrator)

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
**/composer.json
```

**Dependency patterns to match:**

| Language | Dependency Strings |
|----------|-------------------|
| Java | `spring-kafka`, `kafka-clients`, `kafka-streams`, `spring-cloud-stream`, `io.confluent`, `confluent-kafka` |
| Python | `confluent-kafka`, `confluent_kafka`, `kafka-python`, `aiokafka`, `faust-streaming`, `faust` |
| .NET | `Confluent.Kafka`, `Confluent.SchemaRegistry`, `Confluent.SchemaRegistry.Serdes` |
| Go | `confluent-kafka-go`, `github.com/Shopify/sarama`, `github.com/IBM/sarama`, `github.com/segmentio/kafka-go` |
| Node/TS | `kafkajs`, `node-rdkafka`, `@confluentinc/kafka-javascript`, `kafka-node` |
| PHP | `php-rdkafka`, `enqueue/rdkafka`, `longlang/phpkafka`, `jobcloud/php-kafka-lib`, `simple-bus/kafka-publisher` |

### 1.2 Find Producer & Consumer Code

For each app with Kafka dependencies, search source files for producer/consumer patterns.

**Producer detection patterns (grep):**

| Language | Patterns |
|----------|----------|
| Java | `KafkaTemplate`, `KafkaProducer`, `ProducerRecord`, `@SendTo`, `StreamBridge`, `ProducerFactory`, `KStream`, `KTable`, `StreamsBuilder`, `.to(`, `.through(`, `@StreamListener`, `Function<Flux`, `Supplier<`, `spring.cloud.stream.bindings` |
| Python | `Producer(`, `SerializingProducer(`, `AvroProducer(`, `.produce(`, `send(topic`, `send_and_wait(`, `AIOKafkaProducer(` |
| .NET | `ProducerBuilder`, `IProducer`, `ProduceAsync`, `.Produce(` |
| Go | `kafka.NewProducer`, `sarama.NewSyncProducer`, `sarama.NewAsyncProducer`, `kafka.NewWriter` |
| Node/TS | `producer.send(`, `kafka.producer(`, `producer.produce(`, `.sendBatch(` |
| PHP | `$producer->produce(`, `$topic->produce(`, `$producer->send(`, `->produce(`, `ProducerTopic`, `RdKafka\Producer` |

**Consumer detection patterns (grep):**

| Language | Patterns |
|----------|----------|
| Java | `@KafkaListener`, `KafkaConsumer`, `ConsumerRecords`, `KafkaMessageListenerContainer`, `ConcurrentMessageListenerContainer`, `@StreamListener`, `Consumer<Flux`, `spring.cloud.stream.bindings` |
| Python | `Consumer(`, `AvroConsumer(`, `.subscribe(`, `.poll(` |
| .NET | `ConsumerBuilder`, `IConsumer`, `.Consume(`, `ConsumerConfig` |
| Go | `kafka.NewConsumer`, `sarama.NewConsumerGroup`, `sarama.NewConsumer`, `kafka.NewReader`, `.ReadMessage(` |
| Node/TS | `consumer.run(`, `kafka.consumer(`, `consumer.subscribe(`, `eachMessage` |
| PHP | `$consumer->consume(`, `$consumer->subscribe(`, `$consumer->poll(`, `RdKafka\Consumer`, `RdKafka\KafkaConsumer` |

### 1.3 Extract Topic Names

Search for topic names in:
- String literals passed to `send()`, `produce()`, `ProducerRecord`, `@KafkaListener`, `@SendTo`
- Configuration properties: `spring.kafka.template.default-topic`, `TOPIC_NAME`, topic config constants
- YAML/properties files: `spring.kafka.consumer.topics`, `spring.kafka.producer.topic`
- Spring Cloud Stream bindings: `spring.cloud.stream.bindings.{channel}.destination` maps to topic names
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
SpecificAvroSerde
GenericAvroSerde
KafkaJsonSchemaSerde
KafkaProtobufSerde
Serdes.serdeFrom
default.value.serde
default.key.serde
```

**Determine format from serializer:**

| Serializer Found | Schema Format | SR Integrated? |
|-----------------|---------------|----------------|
| `KafkaAvroSerializer` / `AvroSerializer` | AVRO | Yes |
| `KafkaJsonSchemaSerializer` / `JsonSchemaSerializer` | JSON | Yes |
| `KafkaProtobufSerializer` / `ProtobufSerializer` | PROTOBUF | Yes |
| `SpecificAvroSerde` / `GenericAvroSerde` (Kafka Streams) | AVRO | Yes |
| `KafkaJsonSchemaSerde` (Kafka Streams) | JSON | Yes |
| `KafkaProtobufSerde` (Kafka Streams) | PROTOBUF | Yes |
| `HeaderSchemaIdSerializer` | Determined by companion serializer | Yes (SR integrated, header mode) |
| `StringSerializer` + JSON data in code | JSON (infer) | No — flag for upgrade |
| `ByteArraySerializer` + Avro in code | AVRO (infer) | No — flag for upgrade |
| `JsonSerializer` (Spring default) | JSON (infer) | No — flag for upgrade |
| Custom serializer (see 1.4b) | Infer from code | No — flag for upgrade |
| No serializer / raw produce | JSON (infer) | No — flag for upgrade |

**Kafka Streams note:** Streams apps use Serde classes (not Serializer/Deserializer directly). The `default.value.serde` and `default.key.serde` properties in `application.properties` determine the format. Internal topics (changelog, repartition) inherit the default serde. Do NOT generate Terraform for internal topics — they are auto-created by Kafka Streams. Only extract schemas for source and output topics.

**REST Proxy producers:** If the repo makes HTTP POST calls to `/topics/{topic}` or uses `Content-Type: application/vnd.kafka.json.v2+json` (or similar), these are REST Proxy producers. They do not use Kafka client libraries and will not match the dependency patterns in Phase 1.1. Grep for:
```
/topics/
Content-Type.*vnd.kafka
kafka-rest
rest-proxy
```
Classify REST Proxy producers the same way as native producers based on the data format of the HTTP body.

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

**PHP — Custom serializer detection (grep):**
```
json_encode.*produce
json_encode.*send
serialize.*produce
igbinary_serialize
msgpack_pack
```

Look for:
- `json_encode()` called before or inline with `$topic->produce()` or `$producer->produce()`
- Custom serializer classes or functions passed to producer configuration
- `serialize()` / `igbinary_serialize()` / `msgpack_pack()` near produce calls
- Determine format: `json_encode` → JSON, other → flag for review

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

### 1.6 Detect Multi-Schema Topics

After building the app catalog, check if **multiple data models produce to the same topic**.
This happens when different services (or different code paths in the same service) send
different event types to a single topic.

**How to detect:**
1. Group all producers by topic name from the catalog
2. For each topic, check if there are multiple producers with **different** data models
3. Same data model to same topic = normal (just dedup the schema)
4. Different data models to same topic = **multi-schema topic** — requires special handling

**What to look for:**
- Two producers with different generic types: `KafkaTemplate<String, OrderEvent>` and `KafkaTemplate<String, PaymentEvent>` both sending to `"transaction-events"`
- Two services with different Pydantic models / structs producing to the same topic
- A single producer that sends different types conditionally: `if (type == "user") send(topic, userEvent) else send(topic, paymentEvent)`

**When a multi-schema topic is found:**

1. Register each event type as its own subject (not the topic-based subject):
   - e.g., `UserEvent` → subject `user-event`, `PaymentEvent` → subject `payment-event`

2. Create a **wrapper schema** using `oneOf` (JSON Schema), union (Avro), or `oneof` (Protobuf)
   that references the individual event schemas. Register it as the topic subject:

   **JSON Schema wrapper:**
   ```json
   {
     "$schema": "http://json-schema.org/draft-07/schema#",
     "title": "{TopicName}Event",
     "oneOf": [
       { "$ref": "{event-type-1}.json" },
       { "$ref": "{event-type-2}.json" }
     ]
   }
   ```

   **Avro wrapper:**
   ```json
   [
     "{namespace}.EventType1",
     "{namespace}.EventType2"
   ]
   ```

   **Protobuf wrapper:**
   ```protobuf
   import "{event_type_1}.proto";
   import "{event_type_2}.proto";

   message {TopicName}Event {
     oneof event {
       EventType1 type1 = 1;
       EventType2 type2 = 2;
     }
   }
   ```

3. Generate Terraform with `schema_reference` blocks (abbreviated — add `schema_registry_cluster`, `rest_endpoint`, `credentials` per Phase 6.4 template):
   ```hcl
   # Individual event schemas registered first
   resource "confluent_schema" "user_event" {
     subject_name = "user-event"
     format       = "{FORMAT}"
     schema       = file("../schemas/{dir}/user-event.{ext}")
   }

   resource "confluent_schema" "payment_event" {
     subject_name = "payment-event"
     format       = "{FORMAT}"
     schema       = file("../schemas/{dir}/payment-event.{ext}")
   }

   # Wrapper schema with references
   resource "confluent_schema" "{topic}_value" {
     subject_name = "{topic}-value"
     format       = "{FORMAT}"
     schema       = file("../schemas/{dir}/{topic}-value.{ext}")

     schema_reference {
       name         = "{reference_name}"
       subject_name = confluent_schema.user_event.subject_name
       version      = confluent_schema.user_event.version
     }

     schema_reference {
       name         = "{reference_name}"
       subject_name = confluent_schema.payment_event.subject_name
       version      = confluent_schema.payment_event.version
     }
   }
   ```

4. Flag multi-schema topics prominently in the report with a cross-reference table

**Same data model, multiple topics (dedup):**
If the same class produces to multiple topics (e.g., `order-events` and `order-events-dlq`),
generate one schema file and multiple Terraform `confluent_schema` resources pointing to the
same file (abbreviated — add `schema_registry_cluster`, `rest_endpoint`, `credentials` per Phase 6.4):
```hcl
resource "confluent_schema" "order_events_value" {
  subject_name = "order-events-value"
  schema       = file("../schemas/json/order-event.json")
  # ... add schema_registry_cluster, rest_endpoint, credentials, lifecycle
}

resource "confluent_schema" "order_events_dlq_value" {
  subject_name = "order-events-dlq-value"
  schema       = file("../schemas/json/order-event.json")  # same file
  # ... add schema_registry_cluster, rest_endpoint, credentials, lifecycle
}
```

### 1.7 Detect Kafka Connect / Debezium Connectors

Kafka Connect connectors are a major source of Kafka producers in enterprise environments. They run outside application code and are often missed by application-level scans.

**Glob patterns:**
```
**/connect*.properties
**/connect*.json
**/*connector*.json
**/*connector*.yml
**/*connector*.yaml
**/connectors/**
```

**Grep patterns (in config files and source):**
```
connector.class
io.debezium
io.confluent.connect
key.converter
value.converter
AvroConverter
JsonSchemaConverter
ProtobufConverter
JsonConverter
```

**Classification:**

- If `value.converter` uses `AvroConverter`/`JsonSchemaConverter`/`ProtobufConverter` with `schema.registry.url` and `auto.register.schemas=false` (or CP >= 7.x default) → **Category A** (SR-integrated, governed)
- If `value.converter` uses `JsonConverter` without SR → **Category B** (JSON, no SR)
- For sink connectors: record them as **consumers** in the app catalog, not producers. Classify by how they deserialize: if they use a Schema Registry converter, they are SR-integrated consumers.

**Distinguishing application auto-register from connector-native auto-register:**

This distinction is critical. `auto.register.schemas=true` means completely different things depending on where it appears:

| Context | Meaning | Classification |
|---------|---------|----------------|
| Application producer config (Spring Boot properties, Python `ProducerConfig`, .NET `ProducerConfig`, Go `ConfigMap`) | Developer left the default on or didn't know the risk. SR schema evolves silently. Breaking. | **Category C (Application)** — flag as risk, disable immediately |
| Kafka Connect source connector converter config (`key.converter.auto.register.schemas`, `value.converter.auto.register.schemas`) | Connector introspects the source system schema at runtime and must register it. This is by design for source connectors and cannot be disabled without breaking the connector. | **Category C (Connector)** — expected behavior, apply connector governance instead |

**Connector types that require auto-register by design (do NOT flag as misconfiguration):**

| Connector Family | Examples | Why auto-register is required |
|-----------------|----------|-------------------------------|
| CDC connectors | Debezium PostgreSQL, MySQL, SQL Server, Oracle, MongoDB; Confluent JDBC Source | Introspects source table DDL at runtime. Schema is determined by the source DB, not by developer code. Disabling auto-register breaks the connector. |
| File/object source | Confluent S3 Source, GCS Source, Azure Blob Source | Reads schema from file headers or infers from data shape. |
| NoSQL source | MongoDB Atlas Source, DynamoDB Source, Cassandra Source | Source schema is dynamic and schema-inferred at runtime. |
| Replication connectors | MirrorMaker2 (MM2) with SR replication | Mirrors schemas from another SR cluster. Registering them manually would duplicate or conflict. |
| SaaS source connectors | Salesforce Source, ServiceNow Source, Zendesk Source | SaaS schema is owned by the vendor and changes outside developer control. |

**For Category C (Connector) — governance actions (NOT disabling auto-register):**

The goal is not to disable auto-register (that breaks the connector) but to add governance on top of it.

1. **Compatibility mode** — Connector schemas evolve whenever the source system changes (DDL change, new field, dropped field). Set the compatibility mode explicitly per subject via `confluent_subject_config` in Terraform. For CDC connectors, `NONE` or `BACKWARD` is typical since source DDL changes may not be fully backward-compatible. Document the choice.

2. **Subject naming strategy** — Control how connectors name their SR subjects. Configure `value.converter.schema.registry.subject.naming.strategy` (and key variant):
   - `io.confluent.kafka.serializers.subject.TopicNameStrategy` (default): `{topic}-value` — one subject per topic, all table events share a schema
   - `io.confluent.kafka.serializers.subject.RecordNameStrategy`: `{namespace}.{RecordName}` — one subject per record type, regardless of topic
   - `io.confluent.kafka.serializers.subject.TopicRecordNameStrategy`: `{topic}-{RecordName}` — most granular, one subject per topic+record combination; best for CDC where each table maps to its own schema
   - **Recommendation for CDC:** Use `TopicRecordNameStrategy` so each table's schema is independently versioned.

3. **PII tagging** — Source connectors register schemas automatically with no `confluent:tags` because the schema is generated from DB column metadata, not hand-authored. Apply PII tags post-registration:
   - **Terraform:** Generate `confluent_tag_binding` resources that apply `PII`/`PRIVATE` tags to specific fields on specific SR subjects after `confluent_schema` is registered.
   - **Stream Catalog:** Tag fields via the Confluent Cloud UI or Tag Management API (`POST /catalog/v1/types/tagdefs`).
   - **SMT masking (stronger):** If PII must be masked or removed *before* it lands in Kafka (not just tagged for governance), use Kafka Connect Single Message Transforms (SMTs) — `MaskField` to zero-out sensitive columns, `ReplaceField` to drop them, or a custom SMT for pseudonymization.

4. **Schema monitoring** — Enable alerting when a connector registers an unexpected new subject or a new schema version. A new registration means the source system DDL changed. Integrate Schema Registry webhooks or poll the REST API (`GET /subjects/{subject}/versions`) in your monitoring pipeline.

5. **Import into Terraform state** — After the connector has registered schemas, import them into Terraform state so future changes are tracked:
   ```bash
   terraform import confluent_schema.{resource_name} "$SCHEMA_REGISTRY_ID/{subject_name}/latest"
   ```

**For Category C (Application) — standard remediation:**
1. Set `auto.register.schemas=false` in the producer config
2. Register schemas via Terraform (see `terraform/flagged-auto-register.tf`)
3. Set `use.latest.version=true` so the producer fetches the latest registered schema version

Add discovered connectors to the app catalog with `role: connector-source` or `role: connector-sink`. Record the connector family (CDC, file, SaaS, replication) to select the correct governance path.

### 1.8 Detect Key Schemas

Most scans focus on value schemas, but producers with typed keys also need key schemas registered.

**Grep patterns (add to Phase 1.4 scan):**
```
key.serializer
key.deserializer
KeySerializer
key-serializer
key\.serializer
```

**When to extract key schemas:**
- If `key.serializer` is `KafkaAvroSerializer`, `KafkaJsonSchemaSerializer`, or `KafkaProtobufSerializer` → extract the key data model
- If `key.serializer` is `StringSerializer`, `LongSerializer`, `IntegerSerializer`, or `ByteArraySerializer` → no key schema needed
- In Java: the `K` type in `KafkaTemplate<K, V>` or `ProducerRecord<K, V>` is the key model
- In Python: check the `key_serializer` parameter in producer config

For each topic with a typed key, generate a `{topic}-key.{ext}` schema file and a corresponding `confluent_schema` Terraform resource with `subject_name = "{topic}-key"`.

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
AUTO_REGISTER_SCHEMAS.*true
KAFKA_AUTO_REGISTER_SCHEMAS.*true
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
**/docker-compose*.yml
**/docker-compose*.yaml
**/helm/**/values.yaml
**/helm/**/values-*.yaml
**/*deployment*.yaml
**/*configmap*.yaml
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
**/*.avro          (Avro binary data — NOT schema; only read header if no .avsc exists)
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

**PHP — Find data models:**
- Doctrine entities (`#[ORM\Entity]`, `#[ORM\Column]`) used in produce calls
- Laravel Eloquent models (`extends Model`) converted to array/JSON before producing
- Symfony DTOs or readonly classes with typed properties
- PHP 8.2 readonly classes used as event payloads
- Associative arrays passed to `json_encode()` before producing
- Classes with `JsonSerializable` interface implementation

### 3.2b Infer from Inline Key-Value Data (No Class/Model)

If a producer sends data as a raw map, dictionary, or inline JSON object — with no typed class — infer the schema from the code that constructs the data.

**Quick reference — what to look for by data construction pattern:**

| Pattern | Languages | What to Extract |
|---------|-----------|-----------------|
| HashMap / Map.of / dict literal | Java, Python, Go, Node | Field names from keys, types from values |
| JSON string construction | All | Field names from JSON keys in the string |
| JSON tree API (ObjectNode, JsonObject) | Java, .NET | Field names from `.put()` / `.addProperty()` calls |
| Builder / fluent pattern | Java, Kotlin, Scala | Field names from setter method names |
| ORM entity forwarding | All | Field names from entity/model class definition |
| Protobuf builder without SR | Java, Python, Go | Schema from the `.proto` file |
| CSV / delimited strings | All | Infer from variable names (Category D if ambiguous) |

**Detailed patterns by language follow below.** Read only the sections relevant to the languages found in the repo — do not read all of them upfront.

**Java — HashMap / Map.of / JSONObject:**
```
// Detection patterns (grep)
new HashMap<>
Map.of(
Map.ofEntries(
new JSONObject(
put("field_name",
```

Look for:
- `Map<String, Object>` or `HashMap<>` populated with `.put("key", value)` near `send()` / `ProducerRecord`
- `Map.of("key1", val1, "key2", val2)` passed directly to send
- `new JSONObject().put("key", value)` chains
- Infer field names from the string keys in `.put()` calls
- Infer types from the values: string literals → `string`, numeric literals → `number`/`integer`, boolean → `boolean`, variables → trace the variable type

**Python — dict literals / dict construction:**
```
# Detection patterns (grep)
produce.*{
send.*{
json.dumps.*{
dict(
```

Look for:
- Dict literals `{"key": value, ...}` passed to `produce()`, `send()`, or `json.dumps()`
- `dict(key=value, ...)` construction
- Dicts built incrementally: `data = {}; data["key"] = value`
- Infer field names from dict keys, types from values

**Go — map[string]interface{} / map[string]any:**
```
// Detection patterns (grep)
map\[string\]interface
map\[string\]any
```

Look for:
- `map[string]interface{}` or `map[string]any` populated with string keys
- Inline map literals: `map[string]any{"key": value, ...}`
- Infer field names from keys, types from values

**Node/TS — plain objects:**
```
// Detection patterns (grep)
producer.send.*value:.*{
send.*{
```

Look for:
- Object literals passed directly to `producer.send({ value: { key: val, ... } })`
- Variables assigned an object literal then passed to send
- Infer field names from property names, types from values or TypeScript type annotations

**.NET — Dictionary / anonymous objects:**
```
// Detection patterns (grep)
new Dictionary<string
new {
anonymous
```

Look for:
- `Dictionary<string, object>` with `.Add("key", value)` or initializer syntax
- Anonymous objects `new { key = value, ... }` serialized and sent
- Infer field names from keys/properties, types from values

**PHP — Associative arrays:**
```
// Detection patterns (grep)
json_encode.*\[
\[.*=>.*produce
array(.*=>
```

Look for:
- Associative arrays `['key' => value, ...]` passed to `json_encode()` before `produce()`
- `array('key' => value)` syntax
- Arrays built incrementally: `$data['key'] = $value`
- Infer field names from array keys, types from values

**Other inline data patterns to detect (all languages):**

**JSON string construction (manual JSON building):**
```
// Java
String json = "{\"order_id\":\"" + orderId + "\",\"amount\":" + amount + "}";
String.format("{\"order_id\":\"%s\",\"amount\":%f}", orderId, amount);
new StringBuilder().append("{\"order_id\":\"").append(orderId)...

# Python
f'{{"order_id": "{order_id}", "amount": {amount}}}'
'{"order_id": "%s"}' % order_id
"{\"order_id\": \"" + order_id + "\"}"

// Go
fmt.Sprintf(`{"order_id":"%s","amount":%f}`, orderID, amount)

// Node/TS
`{"order_id": "${orderId}", "amount": ${amount}}`
```

Infer field names from the JSON keys in the string. Infer types from the interpolated variables.

**JSON tree / node APIs (building JSON without a class):**
```
// Java — Jackson JsonNode / ObjectNode
ObjectNode node = mapper.createObjectNode();
node.put("order_id", orderId);
node.put("amount", amount);

// Java — Gson JsonObject
JsonObject obj = new JsonObject();
obj.addProperty("order_id", orderId);

// .NET — JObject (Newtonsoft) / JsonNode (System.Text.Json)
var obj = new JObject { ["order_id"] = orderId, ["amount"] = amount };
var node = new JsonObject { ["order_id"] = orderId };

// Go — map or gjson
data := map[string]interface{}{"order_id": id, "amount": amt}
```

Infer fields from `.put()`, `.addProperty()`, or property assignments.

**Builder / fluent patterns:**
```
// Java
Event.builder().orderId(id).amount(amt).build();
new EventBuilder().setOrderId(id).setAmount(amt).build();

// Kotlin
Event(orderId = id, amount = amt)

// Scala
Event(orderId = id, amount = amt)
case class Event(orderId: String, amount: Double)
```

Trace the builder class to find all setter methods — each setter corresponds to a field.

**Database row / ORM object forwarding:**
```
// Java — JPA/Hibernate entity sent to Kafka
kafkaTemplate.send("topic", entity.getId(), objectMapper.writeValueAsString(entity));

# Python — SQLAlchemy / Django model
producer.produce("topic", json.dumps(model.__dict__))
producer.produce("topic", json.dumps(model_to_dict(instance)))

// Go — GORM / sqlx struct
json.Marshal(dbRow)

// Node — Sequelize / Prisma
producer.send({ value: JSON.stringify(dbRecord) })
```

Look for the ORM model / entity class definition — it IS the schema. Extract fields from the entity annotations (`@Column`, `@Field`, model fields).

**Protobuf builders without SR:**
```
// Java
MyEvent.newBuilder().setOrderId(id).setAmount(amt).build();
producer.send(new ProducerRecord<>("topic", event.toByteArray()));

# Python
event = MyEvent()
event.order_id = id
producer.produce("topic", event.SerializeToString())

// Go
event := &pb.MyEvent{OrderId: id, Amount: amt}
data, _ := proto.Marshal(event)
```

The `.proto` file IS the schema — find it via the generated class import path. This is Category E (custom Protobuf serialization without SR).

**CSV / delimited strings:**
```
// Java
String csv = orderId + "," + amount + "," + email;
producer.send(new ProducerRecord<>("topic", csv));

# Python
producer.produce("topic", f"{order_id},{amount},{email}".encode())
```

Look for string joining with delimiters (`,`, `|`, `\t`) near `send()`/`produce()`. Field names are not in the data — check for comments, header rows, or variable names to infer them. This is **Category D** if field names cannot be determined.

**How to build the schema from any of these patterns:**
1. Collect all field names from keys, setters, properties, or interpolated variable names
2. For each field, determine the value type:
   - String literal or `String` variable → `"type": "string"`
   - Integer literal or `int`/`long` variable → `"type": "integer"`
   - Float/double literal → `"type": "number"`
   - Boolean → `"type": "boolean"`
   - Nested map/dict/object → `"type": "object"` with nested properties
   - List/array → `"type": "array"`
   - If type is ambiguous (e.g., `Object`, `interface{}`, `any`), use `{}` (any type in JSON Schema) or `"type": "string"` as a fallback, add a `TODO: verify type` comment, and flag in the report as needing manual review
3. Mark fields as `required` if they are always set (not conditionally)
4. Tag PII fields using the patterns in section 3.3b
5. Classify as **Category B** if schema can be inferred, **Category D** if field names cannot be determined (e.g., raw CSV with no header)

### Schema Format Selection (Audit)

When generating schema files from extracted data models, choose the output format:

1. **If the producer already uses a Confluent SR serializer** → match its format (Avro/JSON/Protobuf)
2. **If existing schema files exist in the repo** (`.avsc`, `.proto`, `.schema.json`) → match that format
3. **If the producer uses a non-SR serializer** (Category B/E) → use the format of the data being serialized:
   - `ObjectMapper` / `json.dumps` / `JSON.stringify` / `json_encode` → JSON Schema
   - `GenericDatumWriter` / `fastavro` / `avro.io` → Avro
   - `proto.Marshal` / `toByteArray()` / `GeneratedMessageV3` → Protobuf
4. **If no signal exists** → default to JSON Schema (no code generation needed)

### 3.3 Convert Data Models to Schemas

For each data model found, generate a schema file. **Tag potential PII fields** with `confluent:tags` (see 3.3b).

**To JSON Schema:**
- Map language types to JSON Schema types: `string→string`, `int/long→integer`, `float/double→number`, `boolean→boolean`, `List→array`, `Map→object`
- Include `required` array for non-nullable fields
- Add `$schema: "http://json-schema.org/draft-07/schema#"`
- Add `title` matching the class/model name
- Add `confluent:tags` to PII fields (see 3.3b)
- **Add `"default"` values** on optional properties for schema evolution safety
- **`additionalProperties`:** Set to `false` only if the subject uses BACKWARD compatibility (SR default). If FORWARD or FULL compatibility is needed, omit `additionalProperties` or set to `true` — otherwise adding new fields in a future version will be rejected as incompatible

Example with PII tags and evolution defaults:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Customer",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "customer_id": { "type": "string" },
    "email": {
      "type": "string",
      "default": "",
      "confluent:tags": ["PII"]
    },
    "phone_number": {
      "type": "string",
      "default": "",
      "confluent:tags": ["PII"]
    },
    "order_total": { "type": "number", "default": 0 }
  },
  "required": ["customer_id", "email"]
}
```

**To Avro:**
- Use `type: "record"` with `namespace` from package/module
- Map types: `String→string`, `int→int`, `long→long`, `float→float`, `double→double`, `boolean→boolean`, `List→array`, `Map→map`
- Use `["null", "type"]` union for nullable/optional fields with `"default": null`
- Add `confluent:tags` to PII fields (see 3.3b)
- **Add defaults for schema evolution** (see below)

**Schema evolution defaults (Avro):** Every optional field MUST have a `default` value. Without defaults, adding or removing fields later will break backward compatibility. Use these defaults by type:
- `string` → `"default": ""`
- `int`, `long` → `"default": 0`
- `float`, `double` → `"default": 0.0`
- `boolean` → `"default": false`
- nullable union `["null", "type"]` → `"default": null`
- `enum` → `"default": "<first symbol>"` (for forward compatibility)

Only the primary key / identifier field(s) should omit a default (they are always required).

Example with PII tags and evolution defaults:
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
      "default": "",
      "confluent:tags": ["PII"]
    },
    {
      "name": "ssn",
      "type": ["null", "string"],
      "default": null,
      "confluent:tags": ["PII", "PRIVATE"]
    },
    { "name": "order_total", "type": "double", "default": 0.0 }
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
  string email = 2 [(confluent.field_meta) = { tags: "PII" }];
  string ssn = 3 [(confluent.field_meta) = { tags: "PII", tags: "PRIVATE" }];
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
| `first_name`, `firstName`, `last_name`, `lastName`, `full_name`, `fullName`, `customer_name`, `user_name`, `person_name`, `display_name` | `PII` | Note: bare `name` has high false-positive rate (matches `product_name`, `server_name`). Only match `name` when prefixed with person-related terms. |
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
| `PII` | Personally Identifiable Information — can identify an individual |
| `PRIVATE` | Highly sensitive — should be encrypted or masked |
| `SENSITIVE` | Sensitive but not directly identifying |
| `PHI` | Protected Health Information (HIPAA) |
| `PUBLIC` | Safe for broad access |

**How to apply tags:**

- **Avro:** Add `"confluent:tags": ["PII"]` as a sibling to `name` and `type` on the field
- **JSON Schema:** Add `"confluent:tags": ["PII"]` as a sibling to `type` on the property
- **Protobuf:** Add `[(confluent.field_meta) = { tags: "PII" }]` after the field number; for multiple tags use `[(confluent.field_meta) = { tags: "PII", tags: "PRIVATE" }]`; must import `confluent/meta.proto`

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
| **A: Compliant** | Uses Confluent serializer + schema.registry.url configured + `auto.register.schemas` is explicitly `false` or absent on client versions where the default is `false` (Java >= 7.x, Python >= 2.0) | Report as compliant. Still extract schema to Terraform if not already managed by IaC. If Terraform files already exist in the repo for these subjects, skip generation. |
| **A→Header: Already on SR, migrating to headers** | Uses Confluent serializer + SR, wants to move schema ID from payload prefix to Kafka headers | No schema extraction needed. Add `HeaderSchemaIdSerializer` to producers. Consumers need no changes — Confluent deserializers on supported versions automatically check both headers and payload for schema ID. See rollout ordering below. |
| **B: Schema in code, no SR** | Has data models/classes but uses StringSerializer, JsonSerializer (Spring), kafka-python, kafkajs raw, or no Confluent SR integration | Extract schema → `terraform/schemas.tf` + add upgrade recommendation to report |
| **C-App: Auto-register (application)** | Application producer has `auto.register.schemas=true` in its own config (Spring Boot properties, Python ProducerConfig, .NET ProducerConfig, Go ConfigMap) | Flag as risk. Extract schema → `terraform/flagged-auto-register.tf` (commented out). Remediation: disable auto-register, register via Terraform, set `use.latest.version=true`. |
| **C-Connector: Auto-register (connector-native)** | Kafka Connect source connector uses `auto.register.schemas=true` in converter config — CDC, JDBC Source, S3 Source, SaaS source, MirrorMaker2, etc. | Expected behavior — do NOT disable. Apply connector governance: set compatibility mode via `confluent_subject_config`, configure subject naming strategy, apply PII tags via `confluent_tag_binding` or SMT, import into Terraform state, enable schema change monitoring. |
| **D: No schema** | Raw strings/bytes where field names and types cannot be reliably determined (e.g., raw CSV without headers, binary protocols, obfuscated data). If inline JSON keys are visible and a schema can be inferred per Section 3.2b, classify as Category B instead | Flag in report with recommendation to adopt schema-first approach |
| **E: Custom serializer** | Implements `Serializer<T>` interface, uses `json.dumps`/`JSON.stringify`/`JsonConvert`/`json.Marshal`/`GenericDatumWriter`/`fastavro`/`proto.Marshal` inline, or has a custom serialization function — all without SR | Extract schema from the data model inside the custom serializer → `terraform/schemas.tf` + recommend replacing with Confluent serializer + `HeaderSchemaIdSerializer`. Consumers must be upgraded first using a composite deserializer pattern (Java). See upgrade rules below. |

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

### 5.5 Schema Compatibility Mode

Include a compatibility mode recommendation for each subject in the report. The compatibility mode determines which schema changes are allowed without breaking consumers.

| Mode | When to Use |
|------|-------------|
| **BACKWARD** (SR default) | Consumers are upgraded before producers. New schema can read old data. Safe to add optional fields with defaults. |
| **FORWARD** | Producers are upgraded before consumers. Old schema can read new data. Safe to remove optional fields. Do NOT use `additionalProperties: false` with JSON Schema. |
| **FULL** | Both directions. Most restrictive — only additive changes with defaults. |
| **NONE** | No compatibility checking. Use only for development/testing. |

Default to BACKWARD unless the user specifies otherwise. Note the recommendation in the Terraform resource as a comment. Compatibility mode is set per-subject in Schema Registry, not in the Terraform `confluent_schema` resource directly — it is configured via `confluent_subject_config` if needed.

---

## Phase 6: Generate Terraform

### 6.1 `terraform/providers.tf`

```hcl
terraform {
  required_version = ">= 1.3.0"

  required_providers {
    confluent = {
      source  = "confluentinc/confluent"
      version = ">= 2.11.0"  # 2.11.0+ required for confluent_tag resources
    }
  }
}

# The Confluent provider v2.x uses per-resource authentication.
# Schema Registry credentials are set on each resource via
# schema_registry_cluster, rest_endpoint, and credentials blocks.
# Alternatively, set these environment variables and omit the blocks:
#   SCHEMA_REGISTRY_ID
#   SCHEMA_REGISTRY_REST_ENDPOINT
#   SCHEMA_REGISTRY_API_KEY
#   SCHEMA_REGISTRY_API_SECRET
provider "confluent" {}
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
  schema_registry_cluster {
    id = var.schema_registry_id
  }
  rest_endpoint = var.schema_registry_rest_endpoint
  credentials {
    key    = var.schema_registry_api_key
    secret = var.schema_registry_api_secret
  }

  name        = "PII"
  description = "Personally Identifiable Information — can identify an individual"
}

resource "confluent_tag" "private" {
  schema_registry_cluster {
    id = var.schema_registry_id
  }
  rest_endpoint = var.schema_registry_rest_endpoint
  credentials {
    key    = var.schema_registry_api_key
    secret = var.schema_registry_api_secret
  }

  name        = "PRIVATE"
  description = "Highly sensitive data — should be encrypted or masked"
}

resource "confluent_tag" "sensitive" {
  schema_registry_cluster {
    id = var.schema_registry_id
  }
  rest_endpoint = var.schema_registry_rest_endpoint
  credentials {
    key    = var.schema_registry_api_key
    secret = var.schema_registry_api_secret
  }

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
  schema_registry_cluster {
    id = var.schema_registry_id
  }
  rest_endpoint = var.schema_registry_rest_endpoint
  credentials {
    key    = var.schema_registry_api_key
    secret = var.schema_registry_api_secret
  }

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
- Replace all non-alphanumeric characters with underscores
- If the result starts with a digit, prefix with `schema_` (Terraform identifiers cannot start with digits)
- Lowercase the entire name
- Prefix with format if multiple formats exist for same topic
- Add `_value` or `_key` suffix
- Examples: `order-events` → `order_events_value`, `3PL.events` → `schema_3pl_events_value`

**Schema references:** If a schema references another (e.g., Avro union types, Protobuf imports), add `schema_reference` blocks:

```hcl
  schema_reference {
    name         = "{referenced_type_name}"
    subject_name = confluent_schema.{referenced_resource}.subject_name
    version      = confluent_schema.{referenced_resource}.version
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
#   schema_registry_cluster {
#     id = var.schema_registry_id
#   }
#   rest_endpoint = var.schema_registry_rest_endpoint
#   credentials {
#     key    = var.schema_registry_api_key
#     secret = var.schema_registry_api_secret
#   }
#
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
# Required environment variables (same as used by the Confluent provider):
#   SCHEMA_REGISTRY_API_KEY
#   SCHEMA_REGISTRY_API_SECRET
#   SCHEMA_REGISTRY_REST_ENDPOINT
#   SCHEMA_REGISTRY_ID
```

Add a `terraform/import.sh` helper script:

```bash
#!/bin/bash
# Import existing schemas from Schema Registry into Terraform state.
# Set these environment variables before running:
#   SCHEMA_REGISTRY_API_KEY
#   SCHEMA_REGISTRY_API_SECRET
#   SCHEMA_REGISTRY_REST_ENDPOINT
#   SCHEMA_REGISTRY_ID
#
# The import ID format is: {sr_cluster_id}/{subject_name}/{schema_version_or_id}
# To find the latest version number for a subject:
#   curl -u "$SCHEMA_REGISTRY_API_KEY:$SCHEMA_REGISTRY_API_SECRET" \
#     "$SCHEMA_REGISTRY_REST_ENDPOINT/subjects/{subject_name}/versions/latest" \
#     | jq '.version'

# {Repeat for each Category A/C schema that is already in SR}
terraform import confluent_schema.{resource_name} "$SCHEMA_REGISTRY_ID/{subject_name}/latest"
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

Replace the custom serializer with a Confluent serializer + `HeaderSchemaIdSerializer`.
The payload format will change, so **consumers must be upgraded first**.

1. Register the schema in Schema Registry via Terraform (already generated in `terraform/schemas.tf`)
2. **Upgrade consumers first** — Java: configure a composite deserializer that can read both the old (custom) format and the new (Confluent) format during the transition. Other languages: coordinated cutover.
3. **Replace the custom serializer** with the appropriate Confluent serializer (`KafkaAvroSerializer`, `ProtobufSerializer`, or `KafkaJsonSchemaSerializer`) and add `HeaderSchemaIdSerializer` to write schema ID to Kafka headers.
4. After all old data has been consumed or expired, replace the composite deserializer with the standard Confluent deserializer.

See detailed upgrade instructions in the "Upgrade Quick Reference — Custom Serializers" section below.

> **Minimum versions required:**
> - Java: CP client >= 8.0
> - Python: confluent-kafka >= 2.10.1
> - Go: confluent-kafka-go >= 2.10.1
> - .NET: Confluent.Kafka >= 2.10.1
> - Node.js: @confluentinc/kafka-javascript >= 1.3.2
>
> **Consumer side — automatic dual-read.** All Confluent client libraries on supported versions automatically check Kafka headers first (`__value_schema_id` / `__key_schema_id`) for the schema ID and fall back to the payload prefix if not found. Once consumers are on the Confluent deserializer, no further config change is needed when producers switch to `HeaderSchemaIdSerializer`.

See per-app upgrade instructions in the "Producer Upgrade Recommendations" section below.

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

Replace the serializer with the Confluent JSON serializer + header-based schema ID.
Payload stays clean JSON. Schema ID goes to Kafka headers. **Non-breaking** for consumers.

> **Minimum versions:** Java CP 8.0+, Python v2.10.1+, .NET v2.10.1+, Go v2.10.1+, Node v1.3.2+.

| Current State | Recommended Serializer | Config Changes |
|--------------|----------------------|----------------|
| Java `StringSerializer` + JSON | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` | Add `value.serializer`, `schema.registry.url`, `value.schema.id.serializer` |
| Java `JsonSerializer` (Spring) | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` | Add Confluent dependency, update serializer class |
| Python `kafka-python` + `json.dumps` | `confluent-kafka` `JSONSerializer` + `header_schema_id_serializer` | Replace library, use `SerializingProducer`, set `value.schema.id.serializer` |
| Python `confluent-kafka` + inline `json.dumps` | `confluent-kafka` `JSONSerializer` + `header_schema_id_serializer` | Remove inline serialization, set `value.schema.id.serializer` |
| .NET `JsonConvert` / `System.Text.Json` | `Confluent.SchemaRegistry.Serdes.Json.JsonSerializer<T>` + header mode | Add NuGet (>= 2.10.1), configure header-based schema ID |
| Go `json.Marshal` before `Produce()` | `confluent-kafka-go` JSON serializer + header mode | Remove manual marshal, add SR client, configure header-based schema ID |
| Node `kafkajs` + `JSON.stringify` | `@confluentinc/kafka-javascript` with SR + header mode | Replace library, remove inline serialization, configure header-based schema ID |
| PHP `json_encode` + `php-rdkafka` | `php-rdkafka` with SR integration + header mode | Add SR client, remove inline `json_encode`, configure header-based schema ID |

### Upgrade Quick Reference — Custom Serializers (Category E)

Replace the custom serializer with a Confluent serializer. The payload format changes, so **consumers must be upgraded first** to handle both old and new formats during the transition.

> **Rollout order: consumers first, then producers.**
> **Minimum versions:** Java CP 8.0+, Python v2.10.1+, .NET v2.10.1+, Go v2.10.1+, Node v1.3.2+.

**Step 1 — Upgrade all consumers (before touching producers):**

The challenge: during migration, the topic contains a mix of old-format messages (produced by the custom serializer — raw JSON with no schema ID) and new-format messages (produced by the Confluent serializer — schema ID in headers). Consumers must handle both until all old data has been consumed or expired.

**IMPORTANT:** `CompositeDeserializer` is a Java-only concept. Each language has its own pattern for dual-format handling. Do not recommend `CompositeDeserializer` for Python, .NET, Go, or Node.js consumers.

---

**Java — Hybrid deserializer using header inspection:**

In Java, implement a `Deserializer<T>` that checks for the `__value_schema_id` header written by `HeaderSchemaIdSerializer`. If found, delegate to `KafkaJsonSchemaDeserializer` (or Avro/Protobuf equivalent). If not, fall back to the legacy custom deserializer.

```java
public class HybridJsonDeserializer<T> implements Deserializer<T> {
    private final KafkaJsonSchemaDeserializer<T> srDeserializer = new KafkaJsonSchemaDeserializer<>();
    private final ObjectMapper legacyMapper = new ObjectMapper();
    private final Class<T> targetType;

    public HybridJsonDeserializer(Class<T> targetType) {
        this.targetType = targetType;
    }

    @Override
    public void configure(Map<String, ?> configs, boolean isKey) {
        srDeserializer.configure(configs, isKey);
    }

    @Override
    public T deserialize(String topic, Headers headers, byte[] data) {
        if (data == null) return null;
        // HeaderSchemaIdSerializer writes schema ID to __value_schema_id header
        if (headers != null && headers.lastHeader("__value_schema_id") != null) {
            return srDeserializer.deserialize(topic, headers, data);
        }
        // No schema ID header → legacy custom format
        try {
            return legacyMapper.readValue(data, targetType);
        } catch (Exception e) {
            throw new SerializationException("Failed to deserialize legacy format", e);
        }
    }

    @Override
    public T deserialize(String topic, byte[] data) {
        // Called without headers — cannot distinguish formats; assume legacy
        try {
            return legacyMapper.readValue(data, targetType);
        } catch (Exception e) {
            throw new SerializationException("Failed to deserialize without headers context", e);
        }
    }
}
```

Configure in Spring Boot:
```properties
spring.kafka.consumer.value-deserializer=com.example.kafka.HybridJsonDeserializer
schema.registry.url=https://your-sr-endpoint
```

For Avro custom serializer migrations, replace `KafkaJsonSchemaDeserializer` with `KafkaAvroDeserializer` and the fallback with `GenericDatumReader` / `SpecificDatumReader`.

---

**Python — Hybrid deserializer with try/except fallback:**

Python has no composite deserializer. Implement a callable deserializer that attempts SR deserialization first (by checking for the schema ID header) and falls back to the legacy format.

```python
import json
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField

sr_client = SchemaRegistryClient({'url': 'https://your-sr-endpoint'})
json_deserializer = JSONDeserializer(schema_str, schema_registry_client=sr_client)

def hybrid_deserializer(data, ctx):
    """Handles both legacy raw JSON (no schema ID) and SR JSON (schema ID in headers)."""
    if data is None:
        return None
    # confluent_kafka exposes headers via ctx if available
    # HeaderSchemaIdSerializer writes '__value_schema_id' to message headers
    headers = getattr(ctx, 'headers', None) or {}
    has_schema_header = any(k == '__value_schema_id' for k, _ in (headers or []))
    if has_schema_header:
        return json_deserializer(data, ctx)
    # Legacy path — raw JSON, no schema ID
    return json.loads(data.decode('utf-8'))

# DeserializingConsumer config:
consumer_conf = {
    'bootstrap.servers': 'broker:9092',
    'group.id': 'my-consumer-group',
    'value.deserializer': hybrid_deserializer,
}
```

Note: if the consumer processes messages from a batch where headers are unavailable, add a magic-byte check: `data[0] == 0x00` indicates a payload-prefix schema ID (non-header mode); absence of the 0x00 magic byte indicates legacy raw format.

---

**.NET — Custom `IDeserializer<T>` with header inspection:**

.NET has no `CompositeDeserializer`. Implement `IDeserializer<T>` manually. The `SerializationContext` passed to `Deserialize()` carries the message headers.

```csharp
using Confluent.Kafka;
using Confluent.SchemaRegistry;
using Confluent.SchemaRegistry.Serdes;
using System.Text;
using System.Text.Json;

public class HybridJsonDeserializer<T> : IDeserializer<T>
{
    private readonly JsonDeserializer<T> _srDeserializer;

    public HybridJsonDeserializer(ISchemaRegistryClient srClient)
    {
        _srDeserializer = new JsonDeserializer<T>(srClient, new JsonDeserializerConfig
        {
            // Header mode: schema ID is read from __value_schema_id header
            SchemaIdLocation = SchemaIdLocation.Header,
        });
    }

    public T Deserialize(ReadOnlySpan<byte> data, bool isNull, SerializationContext context)
    {
        if (isNull) return default!;

        // Check for schema ID header written by HeaderSchemaIdSerializer
        bool hasSchemaHeader = context.Headers?
            .TryGetLastBytes("__value_schema_id", out _) == true;

        if (hasSchemaHeader)
        {
            return _srDeserializer.Deserialize(data, isNull, context);
        }

        // Legacy path — plain JSON, no schema ID
        return JsonSerializer.Deserialize<T>(data,
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
    }
}

// Wire up in consumer builder:
var consumer = new ConsumerBuilder<string, MyType>(consumerConfig)
    .SetValueDeserializer(new HybridJsonDeserializer<MyType>(schemaRegistryClient))
    .Build();
```

For Avro: replace `JsonDeserializer<T>` with `AvroDeserializer<T>` and the legacy fallback with your existing custom deserialization logic.

---

**Go — Hybrid deserializer with header inspection:**

Go has no composite deserializer. Check message headers before choosing the deserialization path. The `confluent-kafka-go` `Message.Headers` slice holds all headers.

```go
import (
    "encoding/json"
    "github.com/confluentinc/confluent-kafka-go/v2/kafka"
    "github.com/confluentinc/confluent-kafka-go/v2/schemaregistry"
    "github.com/confluentinc/confluent-kafka-go/v2/schemaregistry/serde"
    "github.com/confluentinc/confluent-kafka-go/v2/schemaregistry/serde/jsonschema"
)

func hasSchemaIDHeader(msg *kafka.Message) bool {
    for _, h := range msg.Headers {
        if h.Key == "__value_schema_id" {
            return true
        }
    }
    return false
}

func hybridDeserialize[T any](
    msg *kafka.Message,
    srDeserializer *jsonschema.Deserializer,
) (*T, error) {
    if hasSchemaIDHeader(msg) {
        // New format: schema ID in header, delegate to SR deserializer
        result, err := srDeserializer.Deserialize(*msg.TopicPartition.Topic, msg.Value)
        if err != nil {
            return nil, err
        }
        typed, ok := result.(*T)
        if !ok {
            return nil, fmt.Errorf("unexpected type from SR deserializer")
        }
        return typed, nil
    }
    // Legacy format: raw JSON, no schema ID
    var result T
    if err := json.Unmarshal(msg.Value, &result); err != nil {
        return nil, fmt.Errorf("legacy deserialization failed: %w", err)
    }
    return &result, nil
}

// Setup:
srClient, _ := schemaregistry.NewClient(schemaregistry.NewConfig("https://your-sr-endpoint"))
deserializer, _ := jsonschema.NewDeserializer(srClient, serde.ValueSerde, jsonschema.NewDeserializerConfig())

// In consume loop:
msg, _ := consumer.ReadMessage(-1)
result, err := hybridDeserialize[MyType](msg, deserializer)
```

For Avro: replace `jsonschema.NewDeserializer` with `avrov2.NewDeserializer` from `confluent-kafka-go/v2/schemaregistry/serde/avrov2`.

---

**Node.js / TypeScript — Hybrid handler with header inspection:**

`@confluentinc/kafka-javascript` has no composite deserializer. Inspect the `headers` on each message before choosing the deserialization path.

```typescript
import { KafkaJS } from '@confluentinc/kafka-javascript';
import { SchemaRegistryClient, SerdeType } from '@confluentinc/kafka-javascript';

const srClient = new SchemaRegistryClient({ baseUrls: ['https://your-sr-endpoint'] });

async function hybridDeserialize<T>(message: KafkaJS.EachMessagePayload['message']): Promise<T> {
    const headers = message.headers ?? {};
    const hasSchemaHeader = '__value_schema_id' in headers;

    if (hasSchemaHeader) {
        // New format: schema ID in header — use SR deserializer
        const deserializer = srClient.deserializer(SerdeType.VALUE);
        return deserializer.deserialize(message.value!.toString('base64')) as T;
    }

    // Legacy format: plain JSON string, no schema ID
    return JSON.parse(message.value!.toString('utf8')) as T;
}

// In consumer:
await consumer.run({
    eachMessage: async ({ topic, partition, message }) => {
        const event = await hybridDeserialize<MyEventType>(message);
        // process event
    },
});
```

---

**Step 2 — Upgrade all producers:**

Once all consumer instances are deployed with the hybrid deserializer, replace the custom serializer with the Confluent serializer. All new messages will have the schema ID in headers. Old messages (pre-migration) are handled by the legacy fallback in the hybrid deserializer until they expire.

| Language | Replace With | Required Config |
|----------|-------------|-----------------|
| Java | `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer` | `value.serializer`, `schema.registry.url`, `value.schema.id.serializer=io.confluent.kafka.serializers.schema.id.HeaderSchemaIdSerializer` |
| Python | `confluent-kafka` `JSONSerializer` + `HeaderSchemaIdSerializer` | `value.schema.id.serializer=HeaderSchemaIdSerializer()` on `SerializingProducer` |
| .NET | `Confluent.SchemaRegistry.Serdes.JsonSerializer<T>` | `SchemaRegistryConfig { SchemaIdLocation = SchemaIdLocation.Header }` |
| Go | `confluent-kafka-go/v2/schemaregistry/serde/jsonschema.NewSerializer` | `SerializerConfig { EnableHeaders: true }` |
| Node | `@confluentinc/kafka-javascript` with SR + header mode | `SerdeType.VALUE` with `SchemaIdLocation.Header` |
| PHP | `php-rdkafka` with SR integration + header mode | Add SR client, configure header-based schema ID |

**Step 3 — Retire the hybrid deserializer:**

After the topic's retention period has elapsed (all old-format messages have expired), replace the hybrid deserializer with the standard Confluent deserializer on all consumers. Remove the legacy fallback code path entirely.

---

## Migration Rollout Ordering

The order you upgrade producers vs consumers depends on your starting point. Getting this wrong can cause deserialization failures.

### Scenario 1: JSON data, no SR (Category B) — Producers First

Consumers today read raw JSON and ignore Kafka headers. Safe to upgrade producers first.

1. **Upgrade all producers** — switch to Confluent serializer + `HeaderSchemaIdSerializer`. Schema ID goes to headers; payload stays clean JSON. Existing consumers keep working.
2. **Upgrade consumers** — switch to Confluent deserializer. On supported versions, it automatically finds schema ID in headers or payload.

### Scenario 2: Already on SR (Category A→Header) — Producers Only

Consumers already use Confluent deserializers. On supported versions, they automatically check headers first for the schema ID and fall back to the payload prefix. **No consumer changes needed** — just verify consumers are on supported versions.

1. **Verify consumer versions** — Java CP 8.0+, Python v2.10.1+, .NET v2.10.1+, Go v2.10.1+, Node v1.3.2+.
2. **Upgrade producers** — add `HeaderSchemaIdSerializer`. Everything else stays the same.

### Scenario 3: Custom serdes → Confluent serdes (Category E) — Consumers First

The payload format changes when replacing custom serializers with Confluent serializers, so consumers must be upgraded first.

1. **Upgrade all consumers** — Java: configure a composite deserializer (see Category E upgrade above). Other languages: coordinated cutover.
2. **Upgrade all producers** — replace custom serializer with Confluent serializer + `HeaderSchemaIdSerializer`.

---

## Multi-Schema Topics

Topics where multiple event types are produced by different data models.
A wrapper schema with `oneOf`/union/`oneof` has been generated with `schema_reference`
blocks pointing to the individual event schemas.

| Topic | Event Types | Wrapper Schema | References |
|-------|-------------|---------------|------------|
| {topic} | {EventType1}, {EventType2} | schemas/{dir}/{topic}-value.{ext} | {event-type-1}, {event-type-2} |

> If no multi-schema topics are found, omit this section.

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

| Topic | Category | Producers Changing | Active Consumers | Rollout Order | Consumer Action |
|-------|----------|-------------------|-----------------|---------------|-----------------|
| {topic} | B | {app} | {consumers} | Producers first | None during migration — consumers are parsing raw JSON today and will continue to work. After migration completes, upgrade consumers to Confluent deserializer to gain schema validation. |
| {topic} | A→Header | {app} | {consumers} | Producers only | Verify consumer client versions (Java CP 8.0+, Python 2.10.1+, .NET 2.10.1+, Go 2.10.1+, Node 1.3.2+). On supported versions, Confluent deserializers automatically check headers first and fall back to payload prefix. No config change needed. |
| {topic} | C-App | {app} | {consumers} | Producers first (after disabling auto-register) | No consumer changes. Disabling auto-register and registering via Terraform does not change the serialized format. |
| {topic} | C-Connector | {connector} | {consumers} | Connector governance only — no migration | Consumers using Confluent SR deserializers continue working. If consumers use `StringDeserializer`, upgrade them to `KafkaAvroDeserializer` (or JSON/Protobuf equivalent) using the language-specific guidance below. |
| {topic} | E | {app} | {consumers} | **Consumers first** | Deploy hybrid deserializer before touching producers. Language-specific patterns: see below. |

> **Category E — Consumer upgrade is required before producers change.**
> The serialized format changes when replacing a custom serializer with a Confluent serializer.
> Consumers must be able to handle both the old format (no schema ID) and the new format (schema ID in headers)
> during the transition window. See the "Upgrade Quick Reference — Custom Serializers (Category E)" section
> for per-language hybrid deserializer patterns.

**Per-language consumer upgrade summary for Category E:**

| Language | Dual-format strategy | Standard deserializer (post-migration) |
|----------|---------------------|----------------------------------------|
| Java | Implement `Deserializer<T>` that checks `__value_schema_id` header; delegate to `KafkaJsonSchemaDeserializer` if present, else fall back to legacy deserializer | `KafkaJsonSchemaDeserializer` / `KafkaAvroDeserializer` / `KafkaProtobufDeserializer` |
| Python | Callable deserializer with header inspection; try `JSONDeserializer` if header present, else `json.loads()` fallback | `confluent_kafka.schema_registry.json_schema.JSONDeserializer` |
| .NET | Custom `IDeserializer<T>` that inspects `context.Headers` for `__value_schema_id`; delegates to `JsonDeserializer<T>` (header mode) or `JsonSerializer.Deserialize<T>` fallback | `Confluent.SchemaRegistry.Serdes.JsonDeserializer<T>` with `SchemaIdLocation.Header` |
| Go | Helper function that checks `msg.Headers` for `__value_schema_id`; delegates to `jsonschema.Deserializer` or `json.Unmarshal` fallback | `confluent-kafka-go/v2/schemaregistry/serde/jsonschema.NewDeserializer` |
| Node.js | Message handler that checks `message.headers` for `__value_schema_id`; delegates to SR deserializer or `JSON.parse()` fallback | `@confluentinc/kafka-javascript` `SchemaRegistryClient.deserializer()` |

> **`CompositeDeserializer` is Java-only.** Do not recommend it for Python, .NET, Go, or Node.js consumers.
> Each language requires its own dual-format implementation as shown in the upgrade reference section.

---

## Next Steps

1. [ ] Review `schema-report.md` findings with the team
2. [ ] Review and fix all `auto.register.schemas=true` occurrences
3. [ ] Review extracted schemas in `schemas/` for accuracy
4. [ ] Configure Terraform variables (SR cluster ID, endpoint, API credentials)
5. [ ] Run `terraform plan` to preview schema registration
6. [ ] Run `terraform apply` to register schemas
7. [ ] Follow rollout ordering per category (see Migration Rollout Ordering section):
   - Category B: upgrade producers first, then consumers
   - Category A→Header: verify consumer versions, then upgrade producers
   - Category E: upgrade consumers first (composite deserializer for Java), then replace custom serializer with Confluent serializer
8. [ ] For Category E: after all old data is consumed, replace composite deserializer with standard Confluent deserializer
9. [ ] Uncomment `flagged-auto-register.tf` resources after disabling auto-register
10. [ ] Add schema lint/validate to CI/CD pipeline
```

---

## Phase 8: Generate CI/CD Schema Gate

Generate a CI/CD pipeline config that blocks PRs introducing Kafka schema risks. This uses grep-based checks only — no external tool dependencies.

### 8.1 `terraform/ci/schema-lint.yml` (GitHub Actions)

```yaml
name: Kafka Schema Lint
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
      - '**/*Serializer*'
      - '**/*kafka*'
      - '**/*.avsc'
      - '**/*.proto'
      - '**/application*.properties'
      - '**/application*.yml'
      - 'schemas/**'
      - 'terraform/**/*.tf'

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
            --include="*.php" \
            --exclude-dir=docs --exclude-dir=.git --exclude-dir=node_modules \
            --exclude="*.md" --exclude="README*" .; then
            echo "::error::auto.register.schemas=true found — register schemas via Terraform"
            exit 1
          fi

      - name: Warn on StringSerializer for values
        run: |
          if grep -rEi "value.serializer.*StringSerializer|value-serializer.*StringSerializer" \
            --include="*.properties" --include="*.yml" --include="*.java" .; then
            echo "::warning::StringSerializer for values — use KafkaJsonSchemaSerializer + HeaderSchemaIdSerializer"
          fi

      - name: Warn on inline serialization
        run: |
          grep -rn "json\.dumps.*produce\|json\.dumps.*send" --include="*.py" . 2>/dev/null && \
            echo "::warning::Inline json.dumps in Kafka produce — use confluent-kafka serializer" || true
          grep -rn "JSON\.stringify.*send\|JSON\.stringify.*produce" --include="*.ts" --include="*.js" . 2>/dev/null && \
            echo "::warning::Inline JSON.stringify in Kafka send — use Confluent serializer" || true
          grep -rn "json_encode.*produce" --include="*.php" . 2>/dev/null && \
            echo "::warning::Inline json_encode in Kafka produce — use SR integration" || true

      - name: Terraform plan (if Terraform exists)
        if: hashFiles('terraform/*.tf') != ''
        run: |
          cd terraform
          terraform init -backend=false
          terraform validate
```

### 8.2 Include in Report

Add to the report's Next Steps:

```markdown
10. [ ] Copy `terraform/ci/schema-lint.yml` to `.github/workflows/` to enable PR-level schema linting
```

---

## Credential Safety

**NEVER include credential values in any output.** When scanning config files (`application.properties`, `.env`, `docker-compose*.yml`, `*.yml`, `*.yaml`, Kubernetes Secret manifests, Helm `values.yaml`, CI/CD variable definitions), extract ONLY Kafka-related config keys (serializer class, topic name, auto.register setting). Do not copy passwords, API keys, secrets, tokens, or connection strings to any output file (report, schema, Terraform, patches).

If `schema.yaml` is generated with placeholder env vars (`${SCHEMA_REGISTRY_API_KEY}`), warn: "Do not replace these placeholders with actual credentials. They are resolved from environment variables at runtime. Add `schema.yaml` to `.gitignore` if it contains real values."

In the report, reference sensitive config by **file path and line number only** — never reproduce the value. Example: "`basic.auth.user.info` configured at `src/main/resources/application.properties:42`" — never "`basic.auth.user.info=AKIAIOSFODNN7EXAMPLE:wJalrXUtnFEMI/K7MDENG`".

If generating CI/CD pipelines that post reports as PR comments, the report should contain no credential values. If in doubt, omit the value and note "credential configured" instead.

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

- **Monorepos (large):** For repos with 20+ services, process in batches. First scan all build files and rank services by Kafka signal density (most grep hits first). Process the top 10 services, generate partial outputs, then ask the user if they want to continue with remaining services. For Combined mode, skip Discover on services that Audit classified as Category A (fully compliant)
- **Monorepos (general):** Treat each service/module with its own Kafka dependencies as a separate app
- **Multi-topic producers:** Generate one schema resource per topic
- **Shared schemas:** If multiple producers use the same data model for different topics, create one schema file and reference it from multiple Terraform resources. "Same data model" means the same fully-qualified class (Java/Go/.NET) or same module-level class name (Python/Node/PHP). Two different classes with identical fields are separate schemas — note the duplication in the report
- **No topics found:** If topic names are loaded from environment variables or external config and cannot be determined statically, use `TODO-{APP_NAME}-topic-{N}` as the placeholder topic name. In Terraform, add `# TODO: Replace with actual topic name from environment variable {VAR_NAME}`. In the report, add a "Dynamic Topics" section listing each placeholder and the config source it should be resolved from
- **Test code:** Skip test directories (`**/test/**`, `**/tests/**`, `**/__tests__/**`, `**/src/test/**`) unless they contain the only schema/model definitions
- **Multiple serializers per app:** If an app produces to multiple topics with different formats, create separate schema files and Terraform resources for each. If an app has different serializers for different topics, assign a category per `(app, topic)` pair. The app-level category in the summary table should be the worst category (E > D > C > B > A)
- **Unsupported languages (Rust, Ruby, Elixir, etc.):** If the repo contains Kafka usage in languages not listed above, note the unsupported language in the report. Apply the closest supported language's patterns (Kotlin/Scala → Java, Ruby → Python). Mark all findings from unsupported languages as "Low confidence — manual verification required"
- **Polyglot producers:** If different languages produce to the same topic (e.g., Java service and Python service both writing to `order-events`), ensure schema compatibility across languages. Note the language mismatch in the report
- **Transactional producers:** If a producer uses `initTransactions()` / `beginTransaction()` / `commitTransaction()` (Java) or equivalent, note it in the app catalog. Transactional producers may write to multiple topics atomically — group those schemas together in the report
