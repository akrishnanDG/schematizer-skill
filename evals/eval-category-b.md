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

### PII
- `customer_email` tagged as `PII` in both schemas

### Terraform
- 3 `confluent_schema` resources (invoice-event, refund-event, financial-events-value)
- `confluent_tag` resource for PII
- Schema references in wrapper resource

### Report
- Rollout order: **Producers first** (payload stays clean JSON)
- Consumer Impact: "None during migration. Eventually upgrade to Confluent deserializer."
- Multi-schema topic detected and documented

### Assertions
- [ ] Both services classified as Category B
- [ ] 3 schema files generated
- [ ] PII field `customer_email` tagged in both schemas
- [ ] Terraform has `confluent_schema` with `schema_reference` for wrapper
- [ ] Report includes "Producers first" rollout ordering
- [ ] Version numbers: Java 8.1.1+, C/C++ 0.1.0+, Python 2.13.0+, .NET 2.13.0+, Go 2.13.0+, Node 1.8.0+
