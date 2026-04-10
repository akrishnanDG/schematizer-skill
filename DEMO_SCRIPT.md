# Schematizer Skill — Executive Demo Script

> **Duration:** 10-12 minutes
> **Audience:** Engineering leadership, platform team leads, compliance stakeholders
> **Setup:** Claude Code open in the `atlas-banking-platform` repo with schematizer skill installed
> **Model:** Claude Sonnet (`claude --model claude-sonnet-4-6`)
> **Cost per run:** ~$0.20–0.70 (audit), ~$0.10–0.30 (discover)

---

## Opening (30 seconds)

"Atlas Financial has nine backend services and three Kafka Connect connectors. Five languages. Five teams. Kafka is everywhere.

But how many are actually governed? How much PII is flowing through Kafka with no schema contract, no validation, no compliance tagging?

Today I'm going to show you a skill that answers these questions in minutes — and gives you a migration plan, Terraform to register schemas, and a CI/CD pipeline to prevent regressions. Total cost: under a dollar."

---

## Demo 1: Audit Mode — "What risks are hiding?" (5 minutes)

### Prompt

```
Analyze this repo for Kafka applications. Generate schemas, Terraform, and a full report.
```

### What to narrate while it runs

"The skill is scanning all nine services and three Kafka Connect connectors right now. It's looking at build files, Kafka dependencies, serializer configurations, and data models across Java, Python, Go, C#, and TypeScript. The skill itself is only 14,000 tokens — 63% smaller than the original version. We split it into a detection phase and a generation phase so teams can run a quick scan for two cents, or a full audit for under a dollar."

### Key findings to highlight (pause on each)

**1. The scorecard** — Point to the Executive Summary table:

"Out of nine Kafka services and three connectors, only two are fully compliant — compliance-ledger and the S3 sink that reads from it. That's 12.5% governance coverage for a bank."

| Category | Count | Services |
|----------|-------|----------|
| A: Compliant | 2 | compliance-ledger (Java), S3 sink connector |
| C-App: Auto-register risk | 1 | fraud-engine (Java) |
| C-Connector: Auto-register (by design) | 2 | Debezium accounts CDC, Debezium payments CDC |
| D: Wrong library | 1 | customer-portal-events (TypeScript — kafkajs) |
| E: Custom/raw serializer | 5 | payment-gateway (Java), account-service (Python), transaction-router (Go), risk-scoring (.NET), notification-hub (Java consumer) |

**2. The C-App vs C-Connector distinction** — Point to both Risk sections:

"Here's something most governance tools get wrong. The skill flagged `auto.register.schemas=true` in three places — but it classified them differently. The fraud engine is Category C-App: a developer left the flag on, and any code change to `FraudAlert.java` silently registers a new schema version. That's a real risk — disable it, register via Terraform.

But the two Debezium CDC connectors are Category C-Connector. Auto-register is by design — Debezium introspects the database schema at runtime. You can't disable it without breaking the connector. So the skill recommends a different remediation: set explicit compatibility mode, configure subject naming strategy, and apply PII tags post-registration via Stream Catalog. Not every auto-register is the same risk."

**3. The PII exposure** — Point to the PII section:

"The skill found 38 PII fields across 9 schemas. SSNs in two topics. Account numbers in four. IP addresses, emails, device fingerprints, session IDs — all flowing through Kafka with zero field-level governance.

Notice that the schemas themselves are clean — no tags embedded. The PII findings go into separate contract files in `contracts/`. Each contract maps field paths to tags: `*.ssn` gets `PII` and `PRIVATE`, `*.email` gets `PII`. This is intentional — schemas and governance have different lifecycles. Your schema team evolves the data model, your compliance team manages the tags. They don't step on each other.

For a bank under BSA/AML and FDIC oversight, this is a material compliance gap that's been there since the services went to production."

**4. The polyglot problem** — Point to the language breakdown:

"Five different languages, five different Kafka client libraries, five different serialization approaches — none of them consistent. The Java services use custom Jackson serializers. The Python service uses `json.dumps`. The Go service uses `encoding/json`. The C# service uses `System.Text.Json`. The TypeScript service uses `kafkajs` — which isn't even the Confluent client.

The skill generated per-language migration paths. It knows that the .NET consumer needs `Confluent.SchemaRegistry.Serdes.JsonDeserializer<T>` with `SchemaIdLocation.Header`, not a `CompositeDeserializer` — because `CompositeDeserializer` doesn't exist in .NET. It generated hybrid deserializer patterns for every language that needs one."

**5. The multi-schema topic** — Point to the customer-portal-events schema:

"The TypeScript portal service publishes two event types to the same topic — `CustomerEvent` and `ProfileUpdateEvent`. The skill detected this and generated a wrapper schema using JSON Schema `oneOf` with `schema_reference` blocks in Terraform. Multi-schema topics are one of the hardest things to get right manually — here it happened automatically."

**6. The generated artifacts** — Briefly show:

- `schemas/` — "11 pure schemas — 2 Avro, 9 JSON Schema. No tags, no rules, no metadata embedded. Just the data contract."
- `contracts/` — "9 contract files, one per subject. Each maps PII field paths to governance tags. Tags and schemas have separate lifecycles — your compliance team manages these independently."
- `terraform/schemas.tf` — "Registers schemas first. No dependency on tags."
- `terraform/contracts.tf` — "Applies `confluent_tag_binding` per field after schemas exist. Depends on both `tags.tf` and `schemas.tf`."
- `terraform/tags.tf` — "Creates PII, PRIVATE, SENSITIVE tag definitions."
- `terraform/ci/schema-lint.yml` — "GitHub Actions workflow that blocks any PR introducing `auto.register.schemas=true` or raw serialization."

### Punchline

"In five minutes, the skill scanned nine services across five languages and three Kafka Connect connectors. It found:
- 38 untagged PII fields including SSNs
- One application-level auto-register risk and two connector-native ones — classified correctly
- Five custom serializers with no schema contract
- One multi-schema topic
- One wrong Kafka library

It generated 11 clean schemas, 9 contract files with PII tag bindings, Terraform that registers schemas first and applies governance after, a CI/CD gate, and per-language migration guides with hybrid deserializer code for Java, Python, .NET, Go, and Node.js. Schemas and governance are separated by design. All from one prompt, on Sonnet, for under a dollar."

---

## Demo 2: Discover Mode — "Where should we add Kafka?" (3 minutes)

### Prompt

```
Discover where Kafka events should be added in the loan-origination service.
```

### What to narrate while it runs

"The loan origination service has no Kafka at all. It's a REST API backed by JPA. The skill is scanning it for domain models, state transitions, and service methods that would benefit from event streaming."

### Key findings to highlight

**1. The candidates** — Point to the top ranked events:

"The skill found 7 high-confidence event candidates. The top scorer at 17 points is `LoanApplicationApproved` — it found the `LoanApplication` entity with 13 status values, the `approveApplication()` method that's `@Transactional` and calls `loanRepository.save()`, and four financial fields set atomically: `approvedAmount`, `interestRate`, `termMonths`, `decisionDate`.

It then found `LoanApplicationDenied` (score 15), `LoanApplicationSubmitted` (14), `LoanDisbursed`, `CreditCheckCompleted`, `UnderwritingStarted`, and `MarkedDelinquent` — all scoring 13+."

**2. The business reasoning** — Point to the detailed candidate:

"For each candidate it wrote a business question — 'Which loan applications were approved, and at what terms?' — and explained *why Kafka* rather than REST: four downstream services need immediate reaction, REST polling would create tight coupling and SLA risk.

It even identified the specific downstream consumers: notification-hub to send the congratulatory notice, payment-gateway to schedule disbursement, compliance-ledger for GAAP recording, and risk-scoring to update portfolio exposure."

**3. The PII** — Point to the tagged fields:

"8 PII fields: SSN, date of birth, annual income, email, phone, address, first name, last name. The skill flagged `applicant_email` and `applicant_ssn` as EXCLUDED from the event schema — they should be looked up from the customer service, not embedded in the event payload. That's a governance recommendation, not just a tag."

**4. The transactional safety**:

"Every candidate was flagged as medium-risk. The skill recommended `@TransactionalEventListener(phase=AFTER_COMMIT)` for each insertion point — because a Kafka send failure after a database commit would mean a loan was approved but the event was lost. Compliance would have a gap in the audit trail."

**5. The outputs** — Briefly show:

- `kafka_recommendations.yaml` — "404 lines. Every candidate with status `pending_review` — nothing is auto-approved. Teams set each to `approved`, `modified`, `rejected`, or `deferred`."
- `kafka_schemas.yaml` — "Schema stubs for all 7 events with envelope fields and PII tags."
- `patches/loan-origination-kafka-producer.patch` — "A `git apply`-ready patch that adds the Kafka producer to loan-origination. Uses `KafkaJsonSchemaSerializer` + `HeaderSchemaIdSerializer`."

### Punchline

"The skill found seven high-value business events hiding in a JPA service that has zero Kafka today. It ranked them by score, wrote business questions, identified downstream consumers, tagged PII, assessed transactional risk, generated schema stubs, and produced a git-apply-ready patch. And nothing is auto-approved — every candidate requires human review."

---

## Closing (1 minute)

"What you just saw:

1. **Audit** — Scanned nine services across five languages. Found 38 PII fields, one app-level auto-register risk, two connector-native auto-registers classified correctly, five custom serializers, one wrong library, one multi-schema topic. Generated 11 clean schemas, 9 contract files, Terraform, and a CI/CD gate. Schemas and governance are separated — different teams, different lifecycles, same Terraform pipeline.

2. **Discover** — Found seven event candidates in a service with zero Kafka. Ranked by business value, tagged PII, assessed transactional risk, identified downstream consumers, generated a git-apply-ready patch.

3. **Architecture** — The skill is split into tiers: a scan for $0.02 that gives you a governance scorecard, a full audit for under $1 that generates everything, and a discover mode for new services. 63% fewer tokens than the original monolith.

This is what schema governance looks like when it's built into the developer workflow — not a checklist someone fills out after the fact, but an AI skill that reads your code and catches problems before they ship.

The skill works with Claude Code, Cursor, Windsurf — any AI agent. Install it once, and every Kafka producer in your org gets Schema Registry governance by default."

---

## Q&A Prep

**Q: How long does this take on a real repo?**
A: 3-5 minutes for audit on a 9-service repo (what you just saw). 2-3 minutes for discover on a single service. Scan-only takes under a minute. For large monorepos, scope to specific services.

**Q: How much does it cost?**
A: Audit on Sonnet: $0.20–0.70. Discover: $0.10–0.30. Scan-only: ~$0.02. Combined: ~$0.30–1.00. The skill is 14K tokens total (63% reduction from the original), and prompt caching means the skill instructions cost $0.01 on repeat runs.

**Q: Does it actually register schemas?**
A: No — it generates Terraform that you review and apply. Nothing is auto-registered. The migration is human-reviewed and controlled. Same for discover — every candidate requires explicit approval.

**Q: Why are schemas and contracts separate?**
A: Schemas define the data model — that's a developer concern. Contracts define PII tags and governance rules — that's a compliance concern. They evolve on different timelines. A schema change (adding a field) shouldn't require re-tagging PII. A compliance audit updating tags shouldn't require a schema version bump. Terraform registers schemas first, then applies tag bindings as a separate step. If you later need field-level encryption, the ENCRYPT rule and KEK registration layer on top without touching the schema.

**Q: What about field-level encryption?**
A: The skill generates tag bindings by default. CSFLE (Client-Side Field Level Encryption) is opt-in — ask for it explicitly and the skill generates the KEK registration (`confluent_schema_registry_kek`), ENCRYPT rules referencing the KEK by name, and the `kms_type`/`kms_key_id` variables. The KEK must be registered before the ENCRYPT rule or it fails. The DEK is auto-generated by Schema Registry.

**Q: What about existing consumers when we change serializers?**
A: The skill generates per-language hybrid deserializer patterns. During migration, consumers handle both old-format (no schema ID) and new-format (schema ID in headers) messages. Java uses a header-inspecting `Deserializer<T>`. Python, .NET, Go, and Node.js each have their own implementation — the skill generates working code for all five.

**Q: What about Kafka Connect / Debezium?**
A: The skill distinguishes C-App (misconfiguration, fix it) from C-Connector (by design, apply governance). For connectors, it recommends explicit compatibility mode, subject naming strategy, PII tagging via contract files and Stream Catalog, and schema change monitoring. It does NOT tell you to disable auto-register on Debezium — that would break the connector.

**Q: Does it work with Avro, Protobuf, and JSON Schema?**
A: Yes — all three formats. It auto-detects from the existing serializer. Avro is retained for services already using `KafkaAvroSerializer`. JSON Schema is used for raw JSON services — the migration adds `HeaderSchemaIdSerializer` which keeps the payload clean JSON so existing consumers don't break.

**Q: What about the multi-schema topic?**
A: The skill detected `CustomerEvent` and `ProfileUpdateEvent` both publishing to `atlas.customer.events`. It generated individual schemas for each type, a wrapper schema using JSON Schema `oneOf`, and Terraform with `schema_reference` blocks linking them. Each type gets its own contract file for independent PII tagging.

**Q: Can I use it in CI/CD?**
A: Three tiers. Tier 0: the generated `schema-lint.yml` is a pure grep-based GitHub Actions workflow — no Claude, no cost. Tier 1: the scan mode ($0.02) runs as a PR check and outputs a governance scorecard. Tier 2: full audit runs on-demand for migration planning.
