# Eval: Contracts — Schema/contract separation correctness

## Test Prompt

```
Analyze the billing-service, analytics-service, and avro-legacy-service in the test-repo.
Generate schemas, contracts, Terraform, and a full report.
```

## Scope

Any services that produce PII-bearing events, testing that the schema/contract separation is enforced correctly.

## Expected Results

### Schema Purity

Schema files must contain NONE of the following:
- `confluent:tags` (no inline tag annotations)
- `confluent.field_meta` (no field metadata blocks)
- `metadata` top-level key (no metadata envelope)
- `ruleset` top-level key (no rule definitions)
- `ENCRYPT` rules (not present unless explicitly requested)

Schemas are pure data-shape definitions only: types, fields, defaults, descriptions.

### Contract File Format

Each contract file in `contracts/` must:
- Be named `{subject}.contract.json` (subject matches the schema subject)
- Be valid JSON
- Contain a `subject` field (string matching the schema subject name)
- Contain `metadata.tags` (array or object of tag bindings)

### Tag Field Path Syntax

- Tag field paths use `*.field_name` syntax (wildcard prefix)
- Example: `*.customer_email` not `properties.customer_email` or just `customer_email`

### Tag Values

- Tags are from the valid set: `PII`, `PRIVATE`, `SENSITIVE`, `PHI`, `PUBLIC`
- No invented or custom tag names

### Terraform Separation

- `terraform/schemas.tf`:
  - Contains `confluent_schema` resources
  - Schema resources do NOT have `depends_on` referencing tag resources
  - Schemas are registered first in dependency order

- `terraform/contracts.tf`:
  - Contains tag binding resources (e.g., `confluent_tag_binding`)
  - Each binding has `depends_on` referencing both the schema resource and the tag resource
  - Tag bindings are applied after schemas exist

- `terraform/tags.tf`:
  - Contains `confluent_tag` resource definitions
  - Defines PII, PRIVATE, SENSITIVE, etc. as needed

### ENCRYPT Rules

- ENCRYPT rules are NOT present by default
- Only generated if the user explicitly requests encryption
- Schemas and contracts are clean of `ENCRYPT` unless asked

### Assertions

- [ ] Schema files contain NO `confluent:tags`
- [ ] Schema files contain NO `confluent.field_meta`
- [ ] Schema files contain NO `metadata` top-level key
- [ ] Schema files contain NO `ruleset` top-level key
- [ ] Schema files contain NO `ENCRYPT` rules
- [ ] Contract files exist in `contracts/` directory
- [ ] Contract files are named `{subject}.contract.json`
- [ ] Contract files are valid JSON
- [ ] Contract files contain `subject` field (string)
- [ ] Contract files contain `metadata.tags`
- [ ] Tag field paths use `*.field_name` syntax
- [ ] Tags are from valid set: PII, PRIVATE, SENSITIVE, PHI, PUBLIC
- [ ] `terraform/schemas.tf` has `confluent_schema` resources without tag depends_on
- [ ] `terraform/contracts.tf` has tag bindings with `depends_on` schema + tag
- [ ] `terraform/tags.tf` has `confluent_tag` definitions
- [ ] No ENCRYPT rules unless explicitly requested
- [ ] One contract file per schema that has taggable fields
