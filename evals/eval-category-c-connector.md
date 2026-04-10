# Eval: Category C-Connector — Kafka Connect / Debezium connector classification

## Test Prompt

```
Analyze the debezium-connector configs in the test-repo (or atlas-banking-platform) for Kafka usage.
Generate schemas, Terraform, and a full report.
```

## Scope

- Debezium CDC source connectors producing to Schema Registry with `auto.register.schemas=true` (connector default)
- Connector configs (JSON or properties) with `connector.class=io.debezium.connector.postgresql.PostgresConnector` or similar
- Topics follow Debezium naming: `{server}.{schema}.{table}`

## Expected Results

### Categorization
- **C-Connector** (NOT C-App) — connector with auto-register enabled

### Key Distinction from C-App
- Report does NOT recommend disabling `auto.register.schemas` for connectors
- Connector governance section is distinct from application auto-register section
- Connectors legitimately use auto-register as part of their design

### Schemas
- Schema extracted from connector output or Debezium envelope structure
- Schema files contain NO `confluent:tags`, NO `confluent.field_meta`, NO `metadata`, NO `ruleset`

### Contracts
- Contract files generated in `contracts/` with tag bindings for PII fields
- Each contract contains `subject`, `metadata.tags` with `*.field_name` syntax
- Tags from valid set: PII, PRIVATE, SENSITIVE, PHI, PUBLIC

### Report Recommendations
- Compatibility mode configuration (e.g., BACKWARD or FORWARD)
- Subject naming strategy (e.g., `TopicNameStrategy`, `RecordNameStrategy`, or `TopicRecordNameStrategy`)
- PII tagging via contracts (not inline in schemas)
- Schema monitoring (drift detection, version tracking)
- Does NOT include "set auto.register.schemas=false" for connectors

### Terraform
- `terraform/schemas.tf` — schema resources (if extractable)
- `terraform/contracts.tf` — tag binding resources (depends_on schema + tag)
- `terraform/tags.tf` — tag resources for PII, PRIVATE, etc.
- NO `flagged-auto-register.tf` entry for connectors (that file is C-App only)

### Assertions
- [ ] Debezium CDC connectors classified as C-Connector (not C-App)
- [ ] Report does NOT recommend disabling auto.register.schemas for connectors
- [ ] Report recommends compatibility mode configuration
- [ ] Report recommends subject naming strategy
- [ ] Report recommends PII tagging via contracts
- [ ] Report recommends schema monitoring
- [ ] Connector governance section is distinct from application auto-register section
- [ ] Schema files contain NO `confluent:tags` or `confluent.field_meta`
- [ ] Contract files generated in `contracts/` with proper tag bindings
- [ ] No `flagged-auto-register.tf` entry for connector schemas
- [ ] Terraform `contracts.tf` has tag bindings with `depends_on` schema + tag
