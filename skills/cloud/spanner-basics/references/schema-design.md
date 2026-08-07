# Schema Design

Best practices for schema design in Spanner to ensure performance and
scalability.

## Primary Key Design

To avoid creating hotspots, carefully choose a primary key. A common cause of
hotspots is using a key that monotonically increases or decreases (such as a
timestamp) as the first part of the primary key. This directs all insert traffic
to a single server, creating a bottleneck.

### Hotspot Prevention Techniques

#### Use a Universally Unique Identifier (UUID)

*   Recommend using **UUID Version 4** (uses random values).
*   Eliminates hotspots because they don't keep locality between related
    records.
*   Stored in a `UUID` column.

#### Bit-reversed Sequential Values

*   Avoid sequentially increasing/decreasing numerical primary keys.
*   Bit-reverse sequential values to distribute primary key values evenly across
    the key space.
*   Spanner supports bit-reversed sequences.

#### Swap the Order of Keys

*   Spread writes over the key space more uniformly by putting a
    high-cardinality, non-monotonic column first.
*   Example: Order by `UserId` first, then chronological `LastAccess` timestamp.

#### Hash the Unique Key

*   Create a column that contains the hash of the actual unique key.
*   Use the hash column as the primary key to spread writes across logical
    shards.

### Descending Order for Timestamp Keys

Consider using descending order (`DESC`) for timestamp keys if:

*   You want to read the most recent history and are reading the parent row in
    an interleaved table.
*   You are reading sequential entries in reverse chronological order (e.g.,
    most recent N events).

## When to Use an Interleaved Index

*   Avoid creating non-interleaved indexes on columns whose values are
    monotonically increasing or decreasing (like non-primary key timestamps).

*   Use an **interleaved index** where last access rows are interleaved under
    the corresponding user row.

## Data Types

*   **GoogleSQL**: `ARRAY`, `BOOL`, `BYTES`, `DATE`, `ENUM`, `FLOAT32`,
    `FLOAT64`, `INT64`, `JSON`, `NUMERIC`, `PROTO`, `STRING`, `STRUCT`,
    `TIMESTAMP`, `UUID`.
*   **PostgreSQL**: `array`, `bool`, `bytea`, `date`, `float4`, `float8`,
    `int8/bigint`, `jsonb`, `numeric`, `timestamptz`, `uuid`, `varchar/text`.

All types except `FLOAT32`, `ARRAY`, `JSON`, `PROTO`, and `STRUCT` are valid for
primary keys.

## Performance Checklist (Agent Verification)

When reviewing or generating schema-related code, verify the following:

-   [ ] **Hotspot Prevention:** Ensure the first part of the primary key is NOT
    a monotonically increasing or decreasing value (like a sequential ID or
    timestamp). If it is, recommend a UUID (v4), bit-reversed sequence, or
    hashing.
-   [ ] **Interleaved Tables:** Verify if strongly related parent-child data
    that is frequently accessed together is structured using interleaved tables
    (`INTERLEAVE IN PARENT`).
-   [ ] **Interleaving Depth:** Limit interleaving depth. Spanner supports up to
    7 levels of interleaving, but keeping it to a minimum avoids excessive
    overhead.
-   [ ] **Index Design:** Ensure secondary indexes are created for frequent
    query patterns. If sorting by a timestamp is needed, check if the index
    should use descending order (`DESC`).
-   [ ] **Data Types:** Check that the chosen data types are optimal and valid
    for the column's purpose (e.g., `FLOAT32`, `ARRAY`, `JSON`, and `STRUCT`
    cannot be used as primary keys).
