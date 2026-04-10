# Eval: Category E — Custom serializers

## Test Prompt

```
Analyze the analytics-service and avro-legacy-service in the test-repo for Kafka usage.
Generate schemas, Terraform, and a full report.
```

## Scope

- `test-repo/analytics-service` — Java, custom `ClickEventSerializer` (Gson JSON), topic: `click-events`
- `test-repo/avro-legacy-service` — Java, custom `CustomerAvroSerializer` (GenericDatumWriter + BinaryEncoder), topic: `customer-profiles`

## Expected Results

### Categorization
- Both services: **Category E** (custom serializer without SR)

### Schemas
- `schemas/json/click-events-value.json` — JSON Schema from `ClickEvent.java`
- `schemas/avro/customer-profiles-value.avsc` — Avro schema from inline schema in `CustomerProducer.java`
- Schema files contain NO `confluent:tags`, NO `confluent.field_meta`, NO `metadata`, NO `ruleset`

### Contracts
- `contracts/click-events-value.contract.json` — tag bindings for click-events PII
- `contracts/customer-profiles-value.contract.json` — tag bindings for customer-profiles PII
- Each contract contains `subject`, `metadata.tags` with field paths using `*.field_name` syntax

### PII
- `ipAddress` tagged as PII in click-events contract file
- `first_name`, `last_name`, `email`, `phone_number`, `date_of_birth`, `ssn`, `address` tagged as PII in customer-profiles contract file
- `ssn` tagged as both PII and PRIVATE in contract file

### Terraform
- `terraform/schemas.tf` — `confluent_schema` resources for both schemas
- `terraform/contracts.tf` — tag binding resources (depends_on schema + tag)
- `terraform/tags.tf` — `confluent_tag` resources for PII, PRIVATE

### Report
- Recommends **replacing** the custom serializer with Confluent serializer (NOT keeping it)
- Rollout order: **Consumers first** (composite deserializer for Java), then producers
- Does NOT recommend "keep custom serializer + add HeaderSchemaIdSerializer"

### Assertions
- [ ] Both services classified as Category E
- [ ] Schema files contain NO `confluent:tags` or `confluent.field_meta`
- [ ] Contract files generated in `contracts/` with tag bindings
- [ ] Recommendation says to REPLACE custom serializer, not keep it
- [ ] Composite deserializer guidance present for consumer migration
- [ ] Rollout order is "Consumers first"
- [ ] No mention of "keep custom serializer" or "payload stays byte-identical" for Category E
- [ ] SSN tagged as both PII and PRIVATE in contract file (not schema file)
- [ ] Version numbers: Java CP 8.0+, Python v2.10.1+, .NET v2.10.1+, Go v2.10.1+, Node v1.3.2+
