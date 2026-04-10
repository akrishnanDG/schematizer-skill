# Eval: Category B — JSON producers without Schema Registry

## Test Prompt

```
Analyze the billing-service and refund-service in the test-repo for Kafka usage.
Generate schemas, Terraform, and a full report.
```

## Scope

- `test-repo/billing-service` — Java, `StringSerializer` + Jackson `ObjectMapper`, topic: `financial-events`
- `test-repo/refund-service` — Java, `StringSerializer` + Jackson `ObjectMapper`, topic: `financial-events`

## Expected Results

### Categorization
- Both services: **Category B** (schema in code, no SR)

### Schemas
- `schemas/json/invoice-event.json` — JSON Schema from `InvoiceEvent.java`
- `schemas/json/refund-event.json` — JSON Schema from `RefundEvent.java`
- `schemas/json/financial-events-value.json` — Wrapper with `oneOf` (multi-schema topic)
- Schema files contain NO `confluent:tags`, NO `confluent.field_meta`, NO `metadata`, NO `ruleset`

### Contracts
- `contracts/invoice-event.contract.json` — tag bindings for invoice-event
- `contracts/refund-event.contract.json` — tag bindings for refund-event
- `contracts/financial-events-value.contract.json` — tag bindings for wrapper (if applicable)
- Each contract file contains `subject`, `metadata.tags` with field paths using `*.field_name` syntax

### PII
- `customer_email` tagged as `PII` in contract files (NOT in schema files)

### Terraform
- `terraform/schemas.tf` — 3 `confluent_schema` resources (invoice-event, refund-event, financial-events-value)
- `terraform/contracts.tf` — tag binding resources (depends_on schema + tag)
- `terraform/tags.tf` — `confluent_tag` resource for PII
- Schema references in wrapper resource

### Report
- Rollout order: **Producers first** (payload stays clean JSON)
- Consumer Impact: "None during migration. Eventually upgrade to Confluent deserializer."
- Multi-schema topic detected and documented

### Assertions
- [ ] Both services classified as Category B
- [ ] 3 schema files generated — none contain `confluent:tags` or `confluent.field_meta`
- [ ] Contract files generated in `contracts/` with tag bindings
- [ ] PII field `customer_email` tagged in contract files (not schema files)
- [ ] Terraform `schemas.tf` has `confluent_schema` with `schema_reference` for wrapper
- [ ] Terraform `contracts.tf` has tag binding resources with `depends_on` schema + tag
- [ ] Terraform `tags.tf` has `confluent_tag` resource for PII
- [ ] Report includes "Producers first" rollout ordering
- [ ] Version numbers: Java CP 8.0+, Python v2.10.1+, .NET v2.10.1+, Go v2.10.1+, Node v1.3.2+
