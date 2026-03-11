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

### PII
- `ipAddress` tagged as PII (click-events)
- `first_name`, `last_name`, `email`, `phone_number`, `date_of_birth`, `ssn`, `address` tagged as PII (customer-profiles)
- `ssn` tagged as both PII and PRIVATE

### Report
- Recommends **replacing** the custom serializer with Confluent serializer (NOT keeping it)
- Rollout order: **Consumers first** (composite deserializer for Java), then producers
- Does NOT recommend "keep custom serializer + add HeaderSchemaIdSerializer"

### Assertions
- [ ] Both services classified as Category E
- [ ] Recommendation says to REPLACE custom serializer, not keep it
- [ ] Composite deserializer guidance present for consumer migration
- [ ] Rollout order is "Consumers first"
- [ ] No mention of "keep custom serializer" or "payload stays byte-identical" for Category E
- [ ] SSN tagged as both PII and PRIVATE
- [ ] Version numbers correct
