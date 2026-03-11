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
- [ ] Migration Rollout Ordering section present with 3 scenarios
- [ ] Consumer Impact Notes table has correct columns
- [ ] A→Header: no schema extraction, producers only, no consumer changes
- [ ] B: schemas extracted, producers first, JSON stays clean
- [ ] E: schemas extracted, consumers first, replace custom serializer
- [ ] Version numbers consistent across all sections
- [ ] PII fields tagged correctly
- [ ] Terraform generated for B and E only (not A→Header)
- [ ] Report passes `python scripts/validate_output.py`
