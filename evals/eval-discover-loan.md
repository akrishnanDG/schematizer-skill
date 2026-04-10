# Eval: Discover Mode — atlas-banking-platform loan-origination service

## Test Prompt

```
Discover where Kafka events should be added in the atlas-banking-platform/loan-origination service.
Generate recommendations, schema stubs, and code patches.
```

## Scope

- `atlas-banking-platform/loan-origination` — A backend service with no Kafka dependencies, containing:
  - `LoanApplication` entity with a `status` field (13 status values)
  - Multiple mutation methods for loan lifecycle (submit, approve, deny, disburse, mark delinquent, etc.)
  - PII fields for applicant data (SSN, email, phone, DOB, address, names, income)
  - Repository/persistence layer with transactional writes

## Expected Results

### Phase D1: Domain Model Discovery

- 7 high-confidence event candidates found
- `LoanApplication` entity detected with 13 status values (e.g., SUBMITTED, UNDER_REVIEW, APPROVED, DENIED, DISBURSED, DELINQUENT, etc.)
- All mutation methods identified:
  - `submitApplication`
  - `approveApplication`
  - `denyApplication`
  - `disburse`
  - `markDelinquent`
  - (and others — at least 7 total)

### Phase D2: PII Detection

- 8 PII fields detected:
  - `ssn` (PII + PRIVATE)
  - `email` (PII)
  - `phone` (PII)
  - `date_of_birth` (PII)
  - `address` (PII)
  - `first_name` (PII)
  - `last_name` (PII)
  - `annual_income` (SENSITIVE)

### Phase D3: Transactional Safety

- Medium risk flagged for transactional safety
- Outbox pattern recommended (database writes + event publishing should be atomic)
- Report explains dual-write risk and recommends transactional outbox or CDC-based approach

### Phase D4: Outputs

- `discover/kafka_recommendations.yaml`:
  - All candidates have `status: pending_review` (nothing auto-approved)
  - 7 event candidates listed

- `discover/kafka_schemas.yaml`:
  - Schema stubs with envelope fields (event_id, event_type, event_timestamp, event_version, source_service)
  - Schema stubs contain NO `confluent:tags` or `confluent.field_meta`

- Patch file generated:
  - `discover/patches/loan-origination-kafka-producer.patch` (or similar)
  - Uses Confluent serializer + SR
  - Uses `HeaderSchemaIdSerializer` config
  - Includes dependency additions

### Assertions

- [ ] 7 high-confidence event candidates found
- [ ] LoanApplication entity with 13 status values detected
- [ ] 8 PII fields detected (SSN, email, phone, DOB, address, first_name, last_name, annual_income)
- [ ] SSN tagged as PII + PRIVATE
- [ ] annual_income tagged as SENSITIVE
- [ ] All mutation methods identified (submitApplication, approveApplication, denyApplication, disburse, markDelinquent, etc.)
- [ ] Transactional safety flagged as medium risk
- [ ] Outbox pattern recommended
- [ ] `discover/kafka_recommendations.yaml` exists with `pending_review` status on all candidates
- [ ] `discover/kafka_schemas.yaml` exists with envelope fields
- [ ] Schema stubs contain NO `confluent:tags` or `confluent.field_meta`
- [ ] Patch file generated
- [ ] Patch uses Confluent serializer + `HeaderSchemaIdSerializer`
- [ ] No Terraform generated (Discover mode only)
- [ ] Topic names follow naming convention
- [ ] `schema_format` detected from repo context (not hardcoded)
