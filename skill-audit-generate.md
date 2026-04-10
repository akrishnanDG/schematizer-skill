# Kafka Audit — Generate Artifacts

Takes the app catalog from the scan phase and generates schema files, Terraform configuration, a comprehensive governance report, and a CI/CD gate.

**This skill does NOT do detection or classification** — that work is done by `skill-scan.md`. This skill consumes the app catalog output and produces deliverables.

## Input

App catalog from `skill-scan.md` containing for each Kafka application:
- `app_name`, `language`, `role`, `topics`, `serializer_class`
- `schema_format` (AVRO | JSON | PROTOBUF | UNKNOWN)
- `sr_integrated` (true | false), `auto_register` (true | false)
- `category` (A | B | C-App | C-Connector | D | E)
- `custom_serializer` (true | false), `custom_serializer_file`
- Data models / classes identified for schema extraction
- PII field findings from scan phase

## Deliverables

1. **`schemas/`** — Extracted schema files (Avro, JSON Schema, Protobuf) — **pure schema, no tags or rules**
2. **`contracts/`** — Data contract files (`{subject}.contract.json`) with PII tag bindings and rules — **registered after schemas**
3. **`terraform/`** — Terraform configs: `schemas.tf` registers schemas first, `contracts.tf` applies tag bindings and rules after
4. **`schema-report.md`** — Full analysis report with findings, risks, and upgrade recommendations

**Important: Schema files MUST NOT contain `confluent:tags` or `ruleset` blocks.** Tags and rules are governance concerns with a different lifecycle than schema evolution. They belong in contract files, not schema definitions. Terraform registers schemas first (`schemas.tf`), then applies tag bindings and rules (`contracts.tf`) as a separate step.

---

## Pre-Flight: Check for Existing Output

**Before writing any files, check if output directories already exist.** If they do, the skill has been run before and the output may contain manual edits. Overwriting without warning is a data loss risk.

Check for: `schemas/`, `contracts/`, `terraform/`, `schema-report.md`, `scripts/validate-schemas.sh`

**If any exist:**
1. List the existing files found
2. **Ask the user**: "Previous schematizer output found. Overwrite? (y/n)" 
3. If the user says no, stop. If yes, proceed.
4. If running in non-interactive mode (`-p` flag / piped input), **append `-backup` timestamp suffix** to existing directories before writing new output:
   ```
   mv schemas schemas-backup-20260410
   mv contracts contracts-backup-20260410
   mv terraform terraform-backup-20260410
   ```

**If none exist:** proceed normally — first run.

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

contracts/
├── {topic}-value.contract.json
└── ...
```

Schema files contain **only** the schema definition — no `confluent:tags`, no `metadata`, no `ruleset`. Contract files contain the governance layer (tag bindings and rules) and are registered after the schema.

### 5.2 File Naming

- Value schemas: `{topic}-value.{ext}`
- Key schemas (if applicable): `{topic}-key.{ext}`
- Extensions: `.avsc` (Avro), `.json` (JSON Schema), `.proto` (Protobuf)
- Contracts: `{topic}-value.contract.json` (always JSON, regardless of schema format)

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

**If MCP tools are available:** call `schema_lint` with `path: schemas/`, `fix: true` and `schema_validate` with `against: main` (or `live_sr` if SR URL is configured).

**If MCP tools are not available:** skip automated lint/validate. Add to report: "Schemas were not lint-checked or compatibility-validated. Before registering, run `schema_lint` + `schema_validate`, or manually validate using the Confluent Schema Registry REST API."

### 5.5 Schema Compatibility Mode

Include a compatibility mode recommendation for each subject in the report.

| Mode | When to Use |
|------|-------------|
| **BACKWARD** (SR default) | Consumers are upgraded before producers. New schema can read old data. Safe to add optional fields with defaults. |
| **FORWARD** | Producers are upgraded before consumers. Old schema can read new data. Safe to remove optional fields. Do NOT use `additionalProperties: false` with JSON Schema. |
| **FULL** | Both directions. Most restrictive — only additive changes with defaults. |
| **NONE** | No compatibility checking. Use only for development/testing. |

Default to BACKWARD unless the user specifies otherwise. Compatibility mode is set per-subject in Schema Registry via `confluent_subject_config`, not in the `confluent_schema` resource directly.

---

## Schema Conversion Templates

For each data model found in the scan phase, generate a **pure schema file** — no `confluent:tags`, no `metadata`, no `ruleset`. PII tags and rules go in a separate contract file (see "Contract File Generation" below).

**Schema generation MUST be template-based, not LLM-inferred.** Use the exact templates below — substitute only the placeholder values. Do not improvise schema structure, add extra fields, or change the template format.

### Mandatory Rules (all formats)

- **Field naming**: `camelCase` for JSON Schema and Avro, `snake_case` for Protobuf
- **Descriptions**: Every field MUST have a `doc` (Avro) or `description` (JSON Schema)
- **Defaults on ALL optional fields** — every optional field MUST have a default value. Only primary key / identifier field(s) may omit a default.
- **Avro enums**: `UNKNOWN` as first symbol with `"default": "UNKNOWN"` for forward compatibility
- **`additionalProperties: false`** — always set for JSON Schema (BACKWARD is the default compatibility mode)
- **Nullable fields**: JSON Schema uses `["string", "null"]` type array; Avro uses `["null", "string"]` union with `"default": null`
- **Timestamps**: JSON Schema uses `{"type": "string", "format": "date-time"}`; Avro uses `{"type": "long", "logicalType": "timestamp-millis"}`
- **Do NOT add `confluent:tags` or `confluent.field_meta`** to any schema file — tags go in the contract file

### JSON Schema

- Map language types: `string->string`, `int/long->integer`, `float/double->number`, `boolean->boolean`, `List->array`, `Map->object`
- Include `required` array for non-nullable fields
- Add `$schema: "http://json-schema.org/draft-07/schema#"` and `title` matching the class/model name
- Add `"default"` values on optional properties for schema evolution safety
- **`additionalProperties: false`** — always set (BACKWARD is the default compatibility mode). If FORWARD or FULL compatibility is explicitly requested, omit `additionalProperties` or set to `true`
- Add `"description"` on every property
- **Do NOT add `confluent:tags` to schema properties** — tags go in the contract file

Example (clean schema, no tags):
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Customer",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "customerId": { "type": "string", "description": "Unique customer identifier" },
    "email": { "type": "string", "description": "Customer email address", "default": "" },
    "phoneNumber": { "type": ["string", "null"], "description": "Customer phone number", "default": null },
    "orderTotal": { "type": "number", "description": "Total order amount", "default": 0 },
    "createdAt": { "type": "string", "format": "date-time", "description": "Record creation timestamp", "default": "" }
  },
  "required": ["customerId", "email"]
}
```

### Avro

- Use `type: "record"` with `namespace` from package/module
- Map types: `String->string`, `int->int`, `long->long`, `float->float`, `double->double`, `boolean->boolean`, `List->array`, `Map->map`
- Use `["null", "type"]` union for nullable/optional fields with `"default": null`
- Add `"doc"` on every field
- **Do NOT add `confluent:tags` to fields** — tags go in the contract file

**Schema evolution defaults (Avro):** Every optional field MUST have a `default` value. Use these defaults by type:
- `string` -> `"default": ""`
- `int`, `long` -> `"default": 0`
- `float`, `double` -> `"default": 0.0`
- `boolean` -> `"default": false`
- nullable union `["null", "type"]` -> `"default": null`
- `enum` -> `"default": "UNKNOWN"` (UNKNOWN MUST be the first symbol)
- `long` with `logicalType: timestamp-millis` -> `"default": 0`

Only the primary key / identifier field(s) should omit a default.

Example (clean schema, no tags):
```json
{
  "type": "record",
  "name": "Customer",
  "namespace": "com.example.events",
  "fields": [
    { "name": "customerId", "type": "string", "doc": "Unique customer identifier" },
    { "name": "email", "type": "string", "doc": "Customer email address", "default": "" },
    { "name": "ssn", "type": ["null", "string"], "doc": "Social security number", "default": null },
    { "name": "orderTotal", "type": "double", "doc": "Total order amount", "default": 0.0 },
    { "name": "createdAt", "type": { "type": "long", "logicalType": "timestamp-millis" }, "doc": "Record creation timestamp", "default": 0 },
    { "name": "status", "type": { "type": "enum", "name": "Status", "symbols": ["UNKNOWN", "ACTIVE", "INACTIVE"] }, "doc": "Customer status", "default": "UNKNOWN" }
  ]
}
```

### Protobuf

- Use `syntax = "proto3"`
- Map types: `String->string`, `int->int32`, `long->int64`, `float->float`, `double->double`, `boolean->bool`, `List->repeated`, `Map->map<K,V>`
- Use `snake_case` for all field names
- Add `package` from namespace
- Use `google.protobuf.Timestamp` for timestamp fields (add `import "google/protobuf/timestamp.proto";`)
- **Do NOT add `confluent.field_meta` annotations** — tags go in the contract file

Example (clean schema, no tags):
```protobuf
syntax = "proto3";

package com.example.events;

import "google/protobuf/timestamp.proto";

message Customer {
  string customer_id = 1;
  string email = 2;
  string ssn = 3;
  double order_total = 4;
  google.protobuf.Timestamp created_at = 5;
}
```

---

## Contract File Generation

For each schema with PII fields or governance requirements, generate a separate contract file at `contracts/{subject}.contract.json`. Contracts are registered AFTER the schema and contain:

1. **`metadata.tags`** — field-level tag bindings (PII, PRIVATE, SENSITIVE)
2. **`ruleSet`** — optional Data Contract Rules (ENCRYPT, MIGRATE, etc.)

### Contract File Format

```json
{
  "$comment": "Data contract for {subject}. Applied after schema registration.",
  "subject": "{topic}-value",
  "metadata": {
    "tags": {
      "*.email": ["PII"],
      "*.ssn": ["PII", "PRIVATE"],
      "*.phone_number": ["PII"],
      "*.ip_address": ["PII"],
      "*.account_number": ["PII", "PRIVATE"]
    },
    "properties": {
      "owner": "{team_name}",
      "description": "{brief description of the data}"
    }
  }
}
```

**Tag field path syntax:** Use `*.field_name` to match a field at any nesting level. For nested fields, use the full path: `*.address.zip_code`.

**ENCRYPT rules are OPTIONAL.** Only generate ENCRYPT rule stubs if the user explicitly asks for field-level encryption or CSFLE. By default, contracts contain tag bindings only — no ruleSet. Tag bindings alone enable Stream Governance visibility, audit, and policy enforcement without requiring KMS infrastructure.

**When to add ENCRYPT rules (only if requested):** If the user explicitly asks for field-level encryption or CSFLE, and the report identifies PRIVATE fields (SSN, credit card, account numbers), add an ENCRYPT rule stub. The rule references a KEK (Key Encryption Key) by name — the KEK must be registered in Schema Registry via `confluent_schema_registry_kek` before the contract is applied (see `contracts.tf`).

```json
{
  "subject": "{topic}-value",
  "metadata": {
    "tags": {
      "*.ssn": ["PII", "PRIVATE"],
      "*.account_number": ["PII", "PRIVATE"]
    }
  },
  "ruleSet": {
    "domainRules": [
      {
        "name": "encrypt-private-fields",
        "kind": "TRANSFORM",
        "mode": "WRITEREAD",
        "type": "ENCRYPT",
        "tags": ["PRIVATE"],
        "params": {
          "encrypt.kek.name": "pii-encryption-key"
        },
        "onFailure": "ERROR"
      }
    ]
  }
}
```

**Registration order:** KEK → schema (clean) → tag bindings → schema re-registration with metadata + ruleset. The DEK (Data Encryption Key) is auto-generated by Schema Registry — you do not create it.

### PII Tag Mapping (from scan phase)

Use the PII findings from `skill-scan.md` to populate the `metadata.tags` block. Map each detected PII field to its tag:

| PII Pattern | Tags |
|-------------|------|
| `email`, `phone`, `name`, `address`, `dob`, `ip_address` | `["PII"]` |
| `ssn`, `credit_card`, `account_number`, `routing_number`, `passport`, `driver_license` | `["PII", "PRIVATE"]` |
| `salary`, `income`, `gender`, `race`, `ethnicity` | `["SENSITIVE"]` |
| `medical`, `diagnosis`, `prescription` | `["SENSITIVE", "PHI"]` |

### Multi-Schema Topic Wrapper Schemas

When multiple data models produce to the same topic (detected in scan phase), create a wrapper schema using `oneOf` (JSON Schema), union (Avro), or `oneof` (Protobuf) that references the individual event schemas.

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

**Important:** Tag definitions must exist in the catalog before tag bindings can reference them. Generate a `confluent_tag` resource for each tag used in the contract files:

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

Only include tags that are actually used in the contract files. Check the PII tagging results from the scan phase.

### 6.4 `terraform/schemas.tf`

For each Category A, B, and E producer, generate a `confluent_schema` resource. **Schemas are registered first — no `depends_on` for tags.** Tags and rules are applied separately in `contracts.tf` after schemas exist.

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

  lifecycle {
    prevent_destroy = true
  }
}
```

**Resource naming rules:**
- Replace all non-alphanumeric characters with underscores
- If the result starts with a digit, prefix with `schema_` (Terraform identifiers cannot start with digits)
- Lowercase the entire name
- Prefix with format if multiple formats exist for same topic
- Add `_value` or `_key` suffix
- Examples: `order-events` -> `order_events_value`, `3PL.events` -> `schema_3pl_events_value`

**Schema references:** If a schema references another (e.g., Avro union types, Protobuf imports), add `schema_reference` blocks:

```hcl
  schema_reference {
    name         = "{referenced_type_name}"
    subject_name = confluent_schema.{referenced_resource}.subject_name
    version      = confluent_schema.{referenced_resource}.version
  }
```

**Multi-schema topic Terraform with `schema_reference` blocks:**

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

Add `schema_registry_cluster`, `rest_endpoint`, `credentials`, and `lifecycle` blocks per the standard template above.

**Same data model, multiple topics (dedup):** Generate one schema file and multiple `confluent_schema` resources pointing to the same file:
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

If Category A or C producers already have schemas registered in Schema Registry, the Terraform resources will conflict on `terraform apply`. Add import instructions to the report:

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

### 6.8 `terraform/contracts.tf`

**Applied AFTER schemas are registered.** For each schema with PII fields, generate `confluent_tag_binding` resources that apply tags to specific fields. These resources depend on both the tag definitions (from `tags.tf`) and the schema (from `schemas.tf`).

```hcl
# ──────────────────────────────────────────────
# Tag Bindings — applied after schema registration
# Source: contracts/{topic}-value.contract.json
# ──────────────────────────────────────────────

resource "confluent_tag_binding" "{sanitized_topic}_{sanitized_field}_pii" {
  schema_registry_cluster {
    id = var.schema_registry_id
  }
  rest_endpoint = var.schema_registry_rest_endpoint
  credentials {
    key    = var.schema_registry_api_key
    secret = var.schema_registry_api_secret
  }

  tag_name    = "PII"
  entity_name = "${var.schema_registry_id}:${confluent_schema.{sanitized_topic}_value.subject_name}:${confluent_schema.{sanitized_topic}_value.schema_identifier}:{field_name}"
  entity_type = "sr_field"

  depends_on = [
    confluent_tag.pii,
    confluent_schema.{sanitized_topic}_value
  ]
}
```

**Generate one `confluent_tag_binding` resource per field per tag.** If a field has both `PII` and `PRIVATE` tags, generate two binding resources.

**Naming convention:** `{sanitized_topic}_{sanitized_field}_{tag}` — all lowercase, non-alphanumeric replaced with underscores.

**For ENCRYPT rules:** ENCRYPT rules reference a KEK (Key Encryption Key) that **must be registered in Schema Registry before the rule**. Without the KEK, the ENCRYPT rule fails on registration. The order is:

1. Register the KEK via `confluent_schema_registry_kek`
2. Re-register the schema with `metadata` + `ruleset` referencing the KEK

Generate commented-out resources — uncomment after KMS is provisioned and the KEK name/key ID are known:

```hcl
# ──────────────────────────────────────────────
# KMS Key Encryption Key (KEK) — register BEFORE ENCRYPT rules
# Uncomment after provisioning your KMS key (AWS KMS, Azure Key Vault,
# GCP KMS, or HashiCorp Vault).
# ──────────────────────────────────────────────
# resource "confluent_schema_registry_kek" "pii_encryption_key" {
#   schema_registry_cluster {
#     id = var.schema_registry_id
#   }
#   rest_endpoint = var.schema_registry_rest_endpoint
#   credentials {
#     key    = var.schema_registry_api_key
#     secret = var.schema_registry_api_secret
#   }
#
#   name      = "pii-encryption-key"
#   kms_type  = var.kms_type       # "aws-kms", "azure-kms", "gcp-kms", or "hcvault"
#   kms_key_id = var.kms_key_id    # ARN, key URI, or Vault path
#   shared_access = true            # allow all subjects to use this KEK
# }

# ──────────────────────────────────────────────
# Data Contract: {topic_name}-value
# Uncomment after the KEK is registered above.
# The schema body stays identical — only metadata/ruleset are added.
# Order: KEK → schema with ruleset
# ──────────────────────────────────────────────
# resource "confluent_schema" "{sanitized_topic}_value_contract" {
#   subject_name = "{topic}-value"
#   format       = "{FORMAT}"
#   schema       = file("../schemas/{format_dir}/{topic}-value.{ext}")
#
#   metadata {
#     tags = {
#       "*.{pii_field_1}" = ["PII"]
#       "*.{pii_field_2}" = ["PII", "PRIVATE"]
#     }
#   }
#
#   ruleset {
#     domain_rule {
#       name       = "encrypt-private-fields"
#       kind       = "TRANSFORM"
#       mode       = "WRITEREAD"
#       type       = "ENCRYPT"
#       tags       = ["PRIVATE"]
#       params     = {
#         "encrypt.kek.name" = confluent_schema_registry_kek.pii_encryption_key.name
#       }
#       on_failure = "ERROR"
#     }
#   }
#
#   depends_on = [
#     confluent_schema.{sanitized_topic}_value,
#     confluent_schema_registry_kek.pii_encryption_key
#   ]
# }
```

**ENCRYPT rule `params`:** The rule references the KEK by name (`encrypt.kek.name`), not by KMS key ID directly. The KEK resource holds the KMS type and key ID. The DEK (Data Encryption Key) is auto-generated and managed by Schema Registry — you do not create it manually.

**Variables to add to `variables.tf`** when ENCRYPT rules are present:

```hcl
variable "kms_type" {
  description = "KMS provider type: aws-kms, azure-kms, gcp-kms, or hcvault"
  type        = string
  default     = "aws-kms"
}

variable "kms_key_id" {
  description = "KMS key identifier (ARN for AWS, key URI for GCP/Azure, path for Vault)"
  type        = string
  sensitive   = true
}
```

---

## Local Validation

Generate `scripts/validate-schemas.sh` that validates generated schemas locally without a Schema Registry connection.

### JSON Schema validation (requires `jsonschema` or `check-jsonschema` Python package):
```bash
pip install check-jsonschema
for f in schemas/json/*.json; do
  check-jsonschema --check-metaschema "$f" && echo "OK: $f" || echo "FAIL: $f"
done
```

### Avro validation (requires `avro-tools` or maven plugin):

If the repo has a `pom.xml`, generate a `schemas/pom.xml` with the `schema-registry-maven-plugin`:
```xml
<plugin>
  <groupId>io.confluent</groupId>
  <artifactId>kafka-schema-registry-maven-plugin</artifactId>
  <version>7.6.0</version>
  <configuration>
    <schemaTypes>
      <atlas.fraud.alerts-value>AVRO</atlas.fraud.alerts-value>
    </schemaTypes>
    <schemas>
      <atlas.fraud.alerts-value>schemas/avro/atlas.fraud.alerts-value.avsc</atlas.fraud.alerts-value>
    </schemas>
  </configuration>
</plugin>
```

Run: `mvn schema-registry:validate` (validates schema syntax without SR connection when no SR URL is configured)

### Contract validation:
```bash
for f in contracts/*.contract.json; do
  python3 -c "
import json, sys
d = json.load(open('$f'))
assert 'subject' in d, 'missing subject'
assert 'metadata' in d and 'tags' in d['metadata'], 'missing metadata.tags'
for k, v in d['metadata']['tags'].items():
    assert k.startswith('*.'), f'field path {k} must start with *.'
    assert all(t in ('PII','PRIVATE','SENSITIVE','PHI','PUBLIC') for t in v), f'invalid tag in {v}'
print(f'OK: $f')
" || echo "FAIL: $f"
done
```

### Deterministic output verification:
```bash
# Verify no confluent:tags in schema files
grep -rl "confluent:tags" schemas/ && echo "FAIL: schemas contain tags" && exit 1
grep -rl "confluent.field_meta" schemas/ && echo "FAIL: schemas contain field_meta" && exit 1

# Verify all JSON schemas have additionalProperties: false
for f in schemas/json/*.json; do
  python3 -c "
import json
d = json.load(open('$f'))
if d.get('type') == 'object' and 'additionalProperties' not in d:
    print(f'WARN: $f missing additionalProperties')
"
done

# Verify all Avro fields have defaults
for f in schemas/avro/*.avsc; do
  python3 -c "
import json
d = json.load(open('$f'))
for field in d.get('fields', []):
    if 'default' not in field:
        print(f'WARN: $f field {field[\"name\"]} missing default')
"
done
```

### Live Schema Registry compatibility check (requires SR credentials):

If the environment variables `SCHEMA_REGISTRY_URL`, `SCHEMA_REGISTRY_API_KEY`, and `SCHEMA_REGISTRY_API_SECRET` are set, check each generated schema for backward compatibility against the live SR before registration:

```bash
if [ -n "$SCHEMA_REGISTRY_URL" ] && [ -n "$SCHEMA_REGISTRY_API_KEY" ] && [ -n "$SCHEMA_REGISTRY_API_SECRET" ]; then
  echo "=== Live SR Compatibility Check ==="
  SR_AUTH="$SCHEMA_REGISTRY_API_KEY:$SCHEMA_REGISTRY_API_SECRET"
  COMPAT_FAIL=0

  for f in schemas/json/*.json schemas/avro/*.avsc; do
    [ -f "$f" ] || continue
    # Derive subject from filename: atlas.foo.bar-value.json → atlas.foo.bar-value
    subject=$(basename "$f" | sed 's/\.json$//; s/\.avsc$//')

    # Determine schema type
    case "$f" in
      *.avsc) schema_type="AVRO" ;;
      *.json) schema_type="JSON" ;;
    esac

    # Check if subject already exists in SR
    existing=$(curl -s -o /dev/null -w "%{http_code}" -u "$SR_AUTH" \
      "$SCHEMA_REGISTRY_URL/subjects/$subject/versions")

    if [ "$existing" = "200" ]; then
      # Subject exists — check compatibility
      schema_escaped=$(python3 -c "import json; print(json.dumps(json.dumps(json.load(open('$f')))))")
      result=$(curl -s -X POST -u "$SR_AUTH" \
        -H "Content-Type: application/vnd.schemaregistry.v1+json" \
        "$SCHEMA_REGISTRY_URL/compatibility/subjects/$subject/versions/latest" \
        -d "{\"schemaType\":\"$schema_type\",\"schema\":$schema_escaped}")

      is_compat=$(echo "$result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('is_compatible','ERROR'))" 2>/dev/null)

      if [ "$is_compat" = "True" ]; then
        echo "  OK  $subject: compatible with latest version"
      else
        echo "  FAIL  $subject: INCOMPATIBLE with latest version"
        echo "        $result"
        COMPAT_FAIL=1
      fi
    else
      echo "  NEW  $subject: not yet registered (will be created)"
    fi
  done

  if [ "$COMPAT_FAIL" -eq 1 ]; then
    echo ""
    echo "FAIL: One or more schemas are incompatible with the live SR."
    echo "Fix the schema or change the subject compatibility mode before running terraform apply."
    exit 1
  fi
else
  echo "=== Live SR Compatibility Check: SKIPPED ==="
  echo "Set SCHEMA_REGISTRY_URL, SCHEMA_REGISTRY_API_KEY, and SCHEMA_REGISTRY_API_SECRET to enable."
fi
```

Wrap all checks (local validation + live SR compatibility) into the single `scripts/validate-schemas.sh` script. Include it in the report's Next Steps:

```
1. Run `bash scripts/validate-schemas.sh` to verify schemas locally
2. Set SR credentials and re-run to check compatibility against live SR:
   export SCHEMA_REGISTRY_URL=https://psrc-xxxxx.region.aws.confluent.cloud
   export SCHEMA_REGISTRY_API_KEY=<key>
   export SCHEMA_REGISTRY_API_SECRET=<secret>
   bash scripts/validate-schemas.sh
3. Run `terraform plan` then `terraform apply`
```

---

## Phase 7: Generate Report — `schema-report.md`

Create a comprehensive markdown report at the repo root. Use the template below, filling in data from the app catalog.

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
| C-App: Auto-register | N | Application producer with auto.register.schemas=true |
| C-Connector: Auto-register | N | Kafka Connect source connector (by design) |
| D: No schema | N | No discernible schema |
| E: Custom serializer | N | Custom Serializer/inline serialization without SR |

### Minimum Client Versions for Migration

**Always include this block in the report — these are verified minimum versions for HeaderSchemaIdSerializer support:**

> **Minimum versions required:**
> - Java: CP 8.0+
> - Python: confluent-kafka v2.10.1+
> - Go: confluent-kafka-go v2.10.1+
> - .NET: Confluent.Kafka v2.10.1+
> - Node.js: @confluentinc/kafka-javascript v1.3.2+

---

## Applications Discovered

| # | App | Language | Role | Topics | Serializer | SR? | Category |
|---|-----|----------|------|--------|------------|-----|----------|
| 1 | {app_name} | {lang} | producer | {topics} | {serializer} | {yes/no} | {A/B/C/D/E} |

---

## RISKS

### auto.register.schemas=true

> **Impact:** Schema evolution is uncontrolled. Breaking changes can be
> registered without review, potentially breaking all downstream consumers.

| # | App | File | Line | Topics Affected |
|---|-----|------|------|----------------|
| 1 | {app} | {file} | {line} | {topics} |

**Recommendation:**
1. Set `auto.register.schemas=false` in all producer configurations
2. Register schemas via Terraform (see `terraform/flagged-auto-register.tf`)
3. Set `use.latest.version=true` so producers fetch the latest registered schema
4. Add schema validation to CI/CD pipeline

### Custom Serializers Without Schema Registry

> **Impact:** Producers using custom serializer implementations or inline
> serialization bypass Schema Registry entirely. Schema changes are invisible.

| # | App | Custom Serializer | File:Line | Topics Affected | Data Model |
|---|-----|------------------|-----------|----------------|------------|
| 1 | {app} | {class or function name} | {file}:{line} | {topics} | {data class/model} |

---

## Schemas Extracted

| # | Topic | Subject | Format | Source | Schema File |
|---|-------|---------|--------|--------|-------------|
| 1 | {topic} | {topic}-value | {format} | {code model / existing file / inferred} | schemas/{dir}/{file} |

---

## PII Fields Detected

| # | Schema | Field | Tags | Reason |
|---|--------|-------|------|--------|
| 1 | {topic}-value | {field_name} | `PII` | Field name matches PII pattern: email |

> **Total PII fields tagged:** N across M schemas
>
> **Action required:** Review tagged fields for accuracy.

---

## Terraform Resources Generated

| File | Resources | Status |
|------|-----------|--------|
| `terraform/schemas.tf` | N `confluent_schema` resources | Ready to apply |
| `terraform/flagged-auto-register.tf` | N `confluent_schema` resources | Commented out |
| `terraform/import.sh` | N import commands | Run first if schemas already exist in SR |
```

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

### Migration Rollout Ordering

The order you upgrade producers vs consumers depends on your starting point. Getting this wrong can cause deserialization failures.

#### Scenario 1: JSON data, no SR (Category B) — Producers First

Consumers today read raw JSON and ignore Kafka headers. Safe to upgrade producers first.

1. **Upgrade all producers** — switch to Confluent serializer + `HeaderSchemaIdSerializer`. Schema ID goes to headers; payload stays clean JSON. Existing consumers keep working.
2. **Upgrade consumers** — switch to Confluent deserializer. On supported versions, it automatically finds schema ID in headers or payload.

#### Scenario 2: Already on SR (Category A->Header) — Producers Only

Consumers already use Confluent deserializers. On supported versions, they automatically check headers first for the schema ID and fall back to the payload prefix. **No consumer changes needed** — just verify consumers are on supported versions.

1. **Verify consumer versions** — Java CP 8.0+, Python v2.10.1+, .NET v2.10.1+, Go v2.10.1+, Node v1.3.2+.
2. **Upgrade producers** — add `HeaderSchemaIdSerializer`. Everything else stays the same.

#### Scenario 3: Custom serdes -> Confluent serdes (Category E) — Consumers First

The payload format changes when replacing custom serializers with Confluent serializers, so consumers must be upgraded first.

1. **Upgrade all consumers** — Java: configure a composite deserializer (see Category E upgrade above). Other languages: coordinated cutover.
2. **Upgrade all producers** — replace custom serializer with Confluent serializer + `HeaderSchemaIdSerializer`.

---

### Consumer Impact Notes

Include this table in the report for topics where serializer changes may affect consumers:

| Topic | Category | Producers Changing | Active Consumers | Rollout Order | Consumer Action |
|-------|----------|-------------------|-----------------|---------------|-----------------|
| {topic} | B | {app} | {consumers} | Producers first | None during migration — consumers are parsing raw JSON today and will continue to work. After migration completes, upgrade consumers to Confluent deserializer to gain schema validation. |
| {topic} | A->Header | {app} | {consumers} | Producers only | Verify consumer client versions (Java CP 8.0+, Python 2.10.1+, .NET 2.10.1+, Go 2.10.1+, Node 1.3.2+). On supported versions, Confluent deserializers automatically check headers first and fall back to payload prefix. No config change needed. |
| {topic} | C-App | {app} | {consumers} | Producers first (after disabling auto-register) | No consumer changes. Disabling auto-register and registering via Terraform does not change the serialized format. |
| {topic} | C-Connector | {connector} | {consumers} | Connector governance only — no migration | Consumers using Confluent SR deserializers continue working. If consumers use `StringDeserializer`, upgrade them to `KafkaAvroDeserializer` (or JSON/Protobuf equivalent) using the language-specific guidance below. |
| {topic} | E | {app} | {consumers} | **Consumers first** | Deploy hybrid deserializer before touching producers. Language-specific patterns: see below. |

> **Category E — Consumer upgrade is required before producers change.**

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
```
10. [ ] Copy `terraform/ci/schema-lint.yml` to `.github/workflows/` to enable PR-level schema linting
```

---

## Terminology Accuracy

**Use correct Confluent product names.** Do not invent or guess product feature names. Key terms:

| Correct | Incorrect (do not use) |
|---------|----------------------|
| Data Contract Rules | Data Transform Rules, Data Transformation Rules |
| Schema Rules (ENCRYPT rule type) | Field-level encryption rules |
| Stream Governance | Stream Governance Suite, Governance Suite |
| Schema Registry | Schema Registry Service |
| Stream Catalog | Data Catalog, Schema Catalog |
| Tag-Based Policies | Tag Policies |
| `confluent:tags` (field-level) | schema tags, field tags |
| `confluent_tag` / `confluent_tag_binding` (Terraform) | tag_resource, schema_tag |

When recommending field-level encryption for PII, reference: "Data Contract Rules with ENCRYPT rule type and a KMS provider (AWS KMS, Azure Key Vault, GCP KMS, or HashiCorp Vault)."

When referencing PII tag enforcement, use: "`confluent:tags` annotations in schemas, enforced via Tag-Based Policies in Stream Governance."

## Credential Safety

**NEVER include credential values in any output.** When scanning config files (`application.properties`, `.env`, `docker-compose*.yml`, `*.yml`, `*.yaml`, Kubernetes Secret manifests, Helm `values.yaml`, CI/CD variable definitions), extract ONLY Kafka-related config keys (serializer class, topic name, auto.register setting). Do not copy passwords, API keys, secrets, tokens, or connection strings to any output file (report, schema, Terraform, patches).

If `schema.yaml` is generated with placeholder env vars (`${SCHEMA_REGISTRY_API_KEY}`), warn: "Do not replace these placeholders with actual credentials. They are resolved from environment variables at runtime. Add `schema.yaml` to `.gitignore` if it contains real values."

In the report, reference sensitive config by **file path and line number only** — never reproduce the value. Example: "`basic.auth.user.info` configured at `src/main/resources/application.properties:42`" — never "`basic.auth.user.info=AKIAIOSFODNN7EXAMPLE:wJalrXUtnFEMI/K7MDENG`".

If generating CI/CD pipelines that post reports as PR comments, the report should contain no credential values. If in doubt, omit the value and note "credential configured" instead.
