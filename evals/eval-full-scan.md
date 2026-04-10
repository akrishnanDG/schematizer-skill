# Eval: Full scan — All categories

## Test Prompt

```
Analyze the following services in the test-repo:
compliant-avro-service, billing-service, analytics-service, avro-legacy-service.
Generate schemas, Terraform, and a full report.
```

## Scope

All 4 test services covering Categories A→Header, B, and E.

## Expected Results

### Category Breakdown
- A→Header: 1 (compliant-avro-service)
- B: 1 (billing-service)
- E: 2 (analytics-service, avro-legacy-service)

### Schemas & Contracts
- Schema files generated for B and E only (not A→Header)
- All schema files contain NO `confluent:tags`, NO `confluent.field_meta`, NO `metadata`, NO `ruleset`
- Contract files generated in `contracts/` for each schema with tag bindings
- Contract files contain `subject`, `metadata.tags` with `*.field_name` paths

### Terraform
- `terraform/schemas.tf` — schema resources for B and E
- `terraform/contracts.tf` — tag binding resources (depends_on schema + tag)
- `terraform/tags.tf` — tag resources (PII, PRIVATE)
- No Terraform generated for A→Header

### Migration Rollout Ordering
- 3 scenarios documented:
  - Scenario 1 (Category B): Producers first
  - Scenario 2 (Category A→Header): Producers only
  - Scenario 3 (Category E): Consumers first

### Consumer Impact Notes
- Table with columns: Topic, Category, Producers Changing, Active Consumers, Rollout Order, Consumer Action
- Each category has correct rollout order and consumer action

### Assertions
- [ ] All 4 services correctly categorized
- [ ] Schema files contain NO `confluent:tags` or `confluent.field_meta`
- [ ] Contract files generated in `contracts/` with tag bindings
- [ ] Migration Rollout Ordering section present with 3 scenarios
- [ ] Consumer Impact Notes table has correct columns
- [ ] A→Header: no schema extraction, no contracts, producers only, no consumer changes
- [ ] B: schemas extracted (pure), contracts with tags, producers first, JSON stays clean
- [ ] E: schemas extracted (pure), contracts with tags, consumers first, replace custom serializer
- [ ] Terraform has `schemas.tf`, `contracts.tf`, `tags.tf` (separate files)
- [ ] Version numbers consistent across all sections
- [ ] PII fields tagged in contract files (not schema files)
- [ ] Terraform generated for B and E only (not A→Header)
- [ ] Report passes `python scripts/validate_output.py`
