# Bigtable Schema Design Guide for Agents

This document provides guidelines for designing performant schemas.

## Table of Contents

*   [Key concepts](#key-concepts) [L15-L40]
*   [Defining the Row Key Template](#defining-the-row-key-template) [L42-L63]
*   [Structured Row Keys](#structured-row-keys) [L65-L106]
*   [Row Key Design & Hotspotting](#row-key-design--hotspotting) [L108-L128]
*   [Counters for real-time metrics](#counters-for-real-time-metrics)
    [L130-L135]
*   [Materialized views](#materialized-views) [L137-L178]
*   [Performance Checklist (Agent Verification)](#performance-checklist-agent-verification)
    [L180-L197]

## Key concepts

*   **Row key:** Bigtable stores data lexicographically (sorted alphabetically)
    by row key. For best performance queries should be design to filter by row
    key in its entirety or prefix. Point lookups by row key or reading ranges
    starting with a key will be the most performant. Row keys can have multiple
    parts combined using a delimiter, typically following a hierarchical format
    such as `category#subcategory#productID` as in `apparel#shoes#0123`.
    Bigtable doesn't support multi-row transactions but changes within a row are
    transactional. When designing schemas put data that needs to be updated
    transactionally within the same row.
*   **Column Families:** Group data that is accessed together within a row.
    Defined as part of the schema. Contents of a family can easily be deleted in
    bulk with a single command for a given row key.
*   **Column Qualifiers:** Defined at write time. Each row can have as many
    unique qualifiers within the row size limits (256 MB) with no limit on
    number of qualifiers per table. Qualifiers can be used in two ways: 1. as
    attributes in a JSON document e.g. `zipcode`, `city`, `state`, `street
    address` or 2. to store data like affinity scores e.g. `0.9`, `0.7` for
    different products or web pages they visited e.g. `home`, `search`, `cart`.
*   **Timestamps:** Are used for versioning. They are not system timestamps.
    They are user-defined and often used for event times like a sensor reading,
    address change timestamp or date a social media post was written. They can
    be used to expire items using TTL or move them to cold storage for cost
    savings as well as time-travel queries to find the "as of" state of a
    record.

## Defining the Row Key Template

Since Bigtable treats row keys as opaque bytes, you must define a **Row Key
Template** to ensure consistency.

### 1. The Template Format

Define your keys using a placeholder syntax:
`{tenant_id}#{entity_type}#{reversed_timestamp}#{uuid}`

### 2. Implementation Pattern

Use centralized factory functions to construct keys.

*   **Java:** `String.format("%s#%s#%d#%s", tenantId, entity, Long.MAX_VALUE -
    ts, uuid)`
*   **Go:** `fmt.Sprintf("%s#%s#%d#%s", tenantID, entity, math.MaxInt64-ts,
    uuid)`

### 3. Delimiter Selection

Use `#`, `:`, or `|`. Ensure delimiters don't appear in the field data.

## Structured Row Keys

Bigtable supports **Structured Row Keys** to define the structure of your row
keys. This metadata helps external tools (like BigQuery) and the Bigtable SQL
interface understand how to parse your keys.

### Why use Structured Row Keys?

*   **Automatic Parsing:** SQL queries can reference individual segments by name
    instead of using string functions.
*   **Integration:** Improves the experience when querying Bigtable from
    BigQuery or Spark.
*   **Validation:** Helps prevent malformed keys.

### Managing via gcloud

You can define the structure when creating a table or update an existing one:

```bash
gcloud bigtable instances tables update {table_id} \
    --instance=${BIGTABLE_INSTANCE} \
    --row-key-schema-definition-file={row_key_schema_definition_file}
```

Where `{row_key_schema_definition_file}` is a YAML file. A template is provided
in `assets/row_key_schema.yaml`. You can copy this template to create your
schema definition.

## Row Key Design & Hotspotting

If row keys are autoincrement or are prefixed by date or timestamp, all writes
will hit a single node, creating a "hotspot" and killing performance. Bigtable's
in-memory tier addresses hotspotting for reads (e.g. trending content on social
media) but keys should be designed by keeping writes in mind.

### Distribution Strategy

To ensure high performance, agents must validate that row keys are designed for
**high cardinality**.

*   **Avoid:** Sequential timestamps at the start of the key.
*   **Prefer:** Prefixes to divide up the key space or reversed timestamps
    (e.g., `tenantID#reversedTimestamp#objectID`).

#### Field Salting Example

If a user must use a low-cardinality prefix, recommend "salting" the key:
`salt = hash(original_key) % number_of_nodes` `new_row_key = salt + "#" +
original_key`

## Counters for real-time metrics

For frequent updates on single row metrics e.g. number of ad views, social media
post likes, API calls or daily unique viewers (using data sketches like HLL),
create an aggregate family to use Bigtable counters for much higher throughput
and lower latency compared to read-modify-write.

## Materialized views

### For real-time analytics

Materialized views can be used for real-time aggregations across one or more
rows for any type of data including aggregate families (note that approximate
count distinct sketches will need to be aggregated using HLL_COUNT.MERGE).
Frequently used metrics can be pre-aggregated efficiently as these views are
incrementally maintained, then further filtered and aggregated at read time
using SQL. Telemetry, merchant analytics, ad performance monitoring and
real-time features for machine learning are some common use cases. Below is an
example query that can be used as a materialized view that returns hourly count
of messages in each chat room for a messaging application that has chatroom's
unique identifier as the first row key token.

```sql
SELECT SPLIT(_key, '#')[0] AS chatroom, TIMESTAMP_TRUNC(_timestamp, HOUR) AS time_bucket,
COUNT(_key) AS total_messages FROM UNPACK((SELECT * FROM messages(WITH_HISTORY=>TRUE)))
GROUP BY 1, 2
```

### For secondary indexing

Materialized views can be used as asynchronous global secondary indexes. Given
the wide range of SQL functions supported, even geospatial index (using
`S2_CELLIDFROMPOINT`) and inverted index use cases can be served with
materialized views. Below is an example of an inverted index that allows fast
search for rows that have occurrences of a given word in any of its cells in
`user_profile` family or in a particular qualifier .

```sql
SELECT
u.value AS indexed_value,
u.key AS indexed_qualifier,
ARRAY_AGG(_key) AS user_keys
FROM users, UNNEST(MAP_ENTRIES(user_profile)) u
GROUP BY 1,2
```

Filtering this index view for just `indexed_value` returns all occurrences in
the form of an array of row keys from the `users` table while using both
`indexed_value` and `indexed_qualifier` returns results for only that qualifier.

## Performance Checklist (Agent Verification)

When reviewing or generating schema-related code, verify the following:

-   [ ] **Row Key Size:** Must be < 4KB (Ideal: 10–100 bytes). Large keys
    increase memory pressure and disk usage.
-   [ ] **Uniqueness:** Ensure row keys are globally unique. Duplicate keys will
    overwrite existing data.
-   [ ] **Character Set:** Use `^[a-zA-Z0-9\-_#]+$`. Stick to alphanumeric,
    underscores, and hashes. Zero pad all numbers to ensure correct string
    sorting.
-   [ ] **Column Qualifier Size:** Keep < 16 KB to minimize storage footprint.
-   [ ] **Column Family Count:** Limit to < 100 families. Keep names short.
-   [ ] **Cell Field Size:** Keep < 10 MB (100 MB is the hard limit). Larger
    cells slow down retrieval.
-   [ ] **Row Size:** Keep < 100 MB. Note that Bigtable enforces a hard limit of
    256 MB at read time.
