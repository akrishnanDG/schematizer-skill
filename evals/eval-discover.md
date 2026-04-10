# Eval: Discover Mode — Find event candidates in a backend repo

## Test Prompt

```
Discover where Kafka events should be added in the test-repo/order-api directory.
Include patches and report.
```

Note: "Include patches and report" is required to trigger opt-in outputs. Without it, only kafka_recommendations.yaml and kafka_schemas.yaml are generated.

## Scope

- `test-repo/order-api` — A backend service with no Kafka dependencies, containing:
  - `OrderEntity.java` — JPA entity with `status` field (enum: PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED)
  - `OrderService.java` — Service with `createOrder()`, `updateOrderStatus()`, `cancelOrder()` methods calling `orderRepository.save()`
  - `CustomerDTO.java` — DTO with `name`, `email`, `phone`, `address` fields
  - `OrderController.java` — REST controller with POST/PUT/DELETE endpoints

## Expected Results

### Phase D1: Domain Model Discovery

- **Category 1 (DTOs/Entities):** `OrderEntity`, `CustomerDTO` found
- **Category 2 (State fields):** `status` field on `OrderEntity` detected (enum with past-tense values)
- **Category 3 (Mutation methods):** `createOrder()`, `updateOrderStatus()`, `cancelOrder()` in `OrderService`
- **Category 4 (Repository writes):** `orderRepository.save()` calls confirmed
- **Category 5 (Event enums):** `OrderStatus` enum with PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED

### Phase D2: Ranking

- `updateOrderStatus()` should rank highest (mutation + state field + entity + repository write)
- `createOrder()` should rank high (mutation + entity + repository write)
- `cancelOrder()` should rank high (mutation + state field + repository write)

### Phase D3: Business Reasoning

- Each candidate has a `business_question` field
- Topic naming follows `{domain}.{entity}.{action}` convention (e.g., `orders.order.status-changed`)
- Downstream consumers identified or marked as "Unknown"

### Phase D4: Outputs

- `discover/kafka_recommendations.yaml` exists with `pending_review` status on all candidates
- `discover/kafka_schemas.yaml` exists with envelope fields (event_id, event_type, event_timestamp, event_version, source_service)
- `discover/patches/order-api-kafka-producer.patch` exists
- Schema format detected from repo (not hardcoded to JSON)
- Schema stubs contain NO `confluent:tags`, NO `confluent.field_meta`

### Phase D5: Report

- `discover-report.md` exists with executive summary table
- PII fields tagged: `email`, `phone`, `name`, `address` on CustomerDTO

### Assertions

- [ ] At least 3 event candidates identified
- [ ] `updateOrderStatus()` ranks highest or tied for highest
- [ ] All candidates have `status: pending_review` (nothing auto-approved)
- [ ] Schema stubs include all 5 envelope fields
- [ ] Schema stubs contain NO `confluent:tags` or `confluent.field_meta` (purity requirement)
- [ ] PII fields detected and tagged on CustomerDTO
- [ ] Patch file uses Confluent serializer + SR (NOT raw `objectMapper.writeValueAsString`)
- [ ] Patch file uses `HeaderSchemaIdSerializer` config
- [ ] Patch includes required dependency addition (pom.xml or build.gradle hunk)
- [ ] Topic names follow `{domain}.{entity}.{action}` convention
- [ ] `schema_format` field is not hardcoded to "JSON" — detected from repo context
- [ ] `discover-report.md` has executive summary with candidate count and PII count
- [ ] No Terraform generated (Discover mode only — Terraform is Audit mode's job)
