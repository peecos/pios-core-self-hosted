# Neutral Runtime Profile

PIOS Starter is a data-empty Core template. It provides generic runtime and
verification primitives but no active owner service.

The compact profile is:

- Core records use the five zones: originals, events, knowledge, derived, and
  system.
- Logical canonical references use `core://`. Provider locations belong only in
  provenance or storage mappings, never as the canonical meaning of a record.
- Events preserve source/provenance facts. Derived and projection views do not
  silently replace raw or canonical source records.
- Unknown extensions are preserved in raw canonical material where compatible;
  safe purpose-limited projections may reject unsafe fields rather than mutate
  the raw source.
- Health, portability, and source primitives are generic capabilities. They do
  not authorize a source connection, data hydration, application networking, or
  migration.

Before Owner Bind, all owner-sensitive capabilities remain disabled. A passed
health record shows only that the data-empty runtime is structurally healthy.

