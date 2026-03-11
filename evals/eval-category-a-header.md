# Eval: Category A→Header — Already on SR, migrating to headers

## Test Prompt

```
Analyze the compliant-avro-service in the test-repo for Kafka usage.
Generate a full report with upgrade recommendations.
```

## Scope

- `test-repo/compliant-avro-service` — Java, `KafkaAvroSerializer` with SR, `auto.register.schemas=false`, `use.latest.version=true`, no `HeaderSchemaIdSerializer`

## Expected Results

### Categorization
- **Category A→Header** (already on SR, wants to migrate schema ID to headers)

### Schemas
- **No schema extraction** — schemas are already registered in SR

### Report
- Recommends adding `HeaderSchemaIdSerializer` to producer config
- Consumer (`AccountConsumer` with `KafkaAvroDeserializer`) needs NO changes
- Documents automatic dual-read behavior (deserializers check headers first, fall back to payload)
- Rollout order: **Producers only**

### Assertions
- [ ] Service classified as A→Header (not just A)
- [ ] No schema files generated for this service
- [ ] Recommendation: add HeaderSchemaIdSerializer only
- [ ] Consumer action: "None" — automatic dual-read handles it
- [ ] Rollout order is "Producers only"
- [ ] Verify consumer version >= 8.1.1 mentioned
