# Eval: Polyglot — atlas-banking-platform (9 services, 5 languages, 3 connectors)

## Test Prompt

```
Analyze all services in the atlas-banking-platform demo repo for Kafka usage.
Generate schemas, contracts, Terraform, and a full report.
```

## Scope

- `atlas-banking-platform` — 9 services across 5 languages + 3 Kafka Connect connectors:
  - **Java:** compliance-ledger, fraud-engine, payment-gateway, account-service, transaction-router
  - **Python:** risk-scoring
  - **Go:** (one of the above or additional service)
  - **C#/.NET:** (one of the above or additional service)
  - **TypeScript/Node:** customer-portal-events (kafkajs)
  - **Connectors:** 2 Debezium CDC connectors + 1 other

## Expected Results

### Language Detection
- All 5 languages detected: Java, Python, Go, C#, TypeScript

### Categorization
- **Category A:** compliance-ledger (already on SR, well-governed)
- **C-App:** fraud-engine (application with auto-register)
- **C-Connector:** 2 Debezium CDC connectors
- **Category D:** customer-portal-events (kafkajs — raw JSON, no SR)
- **Category E:** payment-gateway, account-service, transaction-router, risk-scoring (custom serializers)

### PII Detection
- 38+ PII fields detected across all services
- PII tagged in contract files only (not in schema files)

### Multi-Schema Topic
- `customer-portal-events` topic detected with multiple event types: `CustomerEvent` + `ProfileUpdateEvent`
- Wrapper schema with `oneOf` generated

### Schemas
- 11+ schema files generated
- All schema files contain NO `confluent:tags`, NO `confluent.field_meta`, NO `metadata`, NO `ruleset`

### Contracts
- 9+ contract files generated in `contracts/`
- Each contract named `{subject}.contract.json`
- Each contains `subject`, `metadata.tags` with `*.field_name` syntax
- Tags from valid set: PII, PRIVATE, SENSITIVE, PHI, PUBLIC

### Terraform
- `terraform/schemas.tf` — schema resources (no depends_on for tags)
- `terraform/contracts.tf` — tag binding resources (depends_on schema + tag)
- `terraform/tags.tf` — tag resources
- `terraform/flagged-auto-register.tf` — commented-out resources for C-App (fraud-engine) only, NOT for C-Connector

### Report
- Per-language hybrid deserializer guidance (Java, Python, Go, C#, TypeScript)
- Rollout ordering per category:
  - Category A: no changes needed
  - C-App: disable auto-register, then Terraform apply
  - C-Connector: compatibility mode + monitoring (no auto-register disable)
  - Category D: producers first (JSON stays clean)
  - Category E: consumers first (composite deserializer)
- Multi-schema topic documented with wrapper strategy

### Assertions
- [ ] All 5 languages detected (Java, Python, Go, C#, TypeScript)
- [ ] compliance-ledger classified as Category A
- [ ] fraud-engine classified as C-App
- [ ] 2 Debezium connectors classified as C-Connector
- [ ] customer-portal-events classified as Category D (kafkajs)
- [ ] payment-gateway, account-service, transaction-router, risk-scoring classified as Category E
- [ ] 38+ PII fields detected
- [ ] Multi-schema topic detected (customer-portal-events: CustomerEvent + ProfileUpdateEvent)
- [ ] 11+ schema files generated — none contain `confluent:tags` or `confluent.field_meta`
- [ ] 9+ contract files generated with tag bindings in `contracts/`
- [ ] Terraform: `schemas.tf`, `contracts.tf`, `tags.tf`, `flagged-auto-register.tf`
- [ ] `flagged-auto-register.tf` contains C-App entries only (not C-Connector)
- [ ] Per-language hybrid deserializer guidance in report
- [ ] Rollout ordering section covers all categories
- [ ] C-Connector section does NOT recommend disabling auto.register.schemas
- [ ] C-App section DOES recommend disabling auto.register.schemas
