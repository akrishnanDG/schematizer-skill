# Eval: Category C — auto.register.schemas=true

## Test Prompt

```
Analyze the auto-register-service in the test-repo for Kafka usage.
Generate schemas, Terraform, and a full report.
```

## Scope

- `test-repo/auto-register-service` — Java, `KafkaAvroSerializer` with SR, `auto.register.schemas=true`, `use.latest.version=true`
- Producer sends `PaymentEvent` to topic `payment-events`
- Has `application.properties` with:
  ```
  spring.kafka.producer.properties.auto.register.schemas=true
  spring.kafka.producer.properties.use.latest.version=true
  spring.kafka.producer.properties.schema.registry.url=https://psrc-abc.us-east-2.aws.confluent.cloud
  ```

## Expected Results

### Categorization
- **Category C** (auto-register enabled)

### Phase 2: Risk Detection
- `auto.register.schemas=true` found at specific file:line
- `use.latest.version=true` also detected (noted as easing migration)

### Schemas
- Schema extracted from `PaymentEvent.java` data model
- Schema file: `schemas/avro/payment-events-value.avsc` (or json/ depending on serializer)
- Schema includes evolution defaults (default values on optional fields)

### Terraform
- `terraform/flagged-auto-register.tf` generated with **commented-out** `confluent_schema` resource
- Comment block explains:
  1. Set `auto.register.schemas=false`
  2. Uncomment the resource
  3. Run `terraform apply`
  4. Set `use.latest.version=true` (already set — noted in report)
- `terraform/schemas.tf` does NOT contain this schema (it goes in flagged file only)
- `terraform/import.sh` includes import command (schema likely already in SR from auto-register)

### Report
- Risk section prominently flags `auto.register.schemas=true`
- Notes that `use.latest.version=true` is already set (migration step 4 already done)
- Includes file path and line number where auto-register was found

### PII Detection
- `customer_email` tagged as PII if present in PaymentEvent

### Assertions
- [ ] Service classified as Category C (not A or B)
- [ ] `auto.register.schemas=true` detected with file:line reference
- [ ] `use.latest.version=true` detected and noted as migration aid
- [ ] Schema extracted with evolution defaults (default values on optional fields)
- [ ] Terraform resource is in `flagged-auto-register.tf` (NOT `schemas.tf`)
- [ ] Terraform resource is **commented out**
- [ ] Comment block includes 4-step migration instructions
- [ ] `import.sh` includes import command for this schema
- [ ] Report risk section flags auto-register with impact explanation
- [ ] Report notes that `use.latest.version=true` is already configured
