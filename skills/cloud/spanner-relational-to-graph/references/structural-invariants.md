# Spanner Graph DDL Structural Invariants & Compiler Error Prevention

## Table of Contents

- [1. Unique Element Table Aliases Across Nodes and Edges](#1-unique-element-table-aliases-across-nodes-and-edges):
  Lines 27-45
- [2. `REFERENCES` Must Target the Node Alias](#2-references-must-target-the-node-alias-never-the-label-or-unaliased-table-name):
  Lines 47-55
- [3. Shared Labels Must Have Identical Property Signatures](#3-shared-labels-must-have-identical-property-signatures):
  Lines 57-71
- [4. Reference the Full Node Key, With Matching Types](#4-reference-the-full-node-key-with-matching-types-source-key-and-destination-key):
  Lines 73-101
- [5. Explicit, Unique `KEY` Clause on SQL Bridge Views](#5-explicit-unique-key-clause-on-sql-bridge-views-or-validate_element_key_uniqueness):
  Lines 103-133
- [6. One Data Type per Property Name Across the Entire Graph](#6-one-data-type-per-property-name-across-the-entire-graph):
  Lines 135-152
- [7. Every View Needs a `SQL SECURITY` Clause](#7-every-view-needs-a-sql-security-clause-invoker-vs-definer):
  Lines 154-166
- [8. Custom `KEY` Clause on a Table Must Contain the Primary Key or Match a Unique Index](#8-custom-key-clause-on-a-table-must-contain-the-primary-key-or-match-a-unique-index-and-avoid-null-keys):
  Lines 168-186

Before outputting or applying a `CREATE PROPERTY GRAPH` DDL statement, verify
all 8 invariants below. The quoted messages are the actual Spanner errors
(verified against a live instance); where Spanner does **not** reject a mistake,
the invariant says so explicitly.

## 1. Unique Element Table Aliases Across Nodes and Edges

- **Compiler Error**:
  `The node table '{alias_name}' is defined more than once; use a unique name`
- **Cause**: Using the same relational table in `NODE TABLES` and `EDGE TABLES`
  (or multiple times in `EDGE TABLES`) without unique `AS {alias_name}` names.
- **Fix**: Assign a distinct `AS` alias to every node and edge entry:
  ```sql
  NODE TABLES (
    Accounts AS Account KEY (account_id) LABEL Account PROPERTIES (account_id, balance)
  )
  EDGE TABLES (
    Accounts AS AccountParentEdge
      KEY (account_id)
      SOURCE KEY (account_id) REFERENCES Account(account_id)
      DESTINATION KEY (parent_account_id) REFERENCES Account(account_id)
      LABEL HAS_PARENT NO PROPERTIES
  )
  ```

## 2. `REFERENCES` Must Target the Node Alias (Never the Label or Unaliased Table Name)

- **Compiler Error**:
  `The referenced node table '{name}' is not defined in the property graph`
- **Cause**: Writing `REFERENCES Accounts(account_id)` when the node table was
  aliased as `Accounts AS Account`, or referencing the `LABEL` name when it
  differs from the `AS` alias.
- **Fix**: Ensure every `REFERENCES {node_alias}(...)` in `EDGE TABLES` matches
  the exact `AS {node_alias}` declared in `NODE TABLES`.

## 3. Shared Labels Must Have Identical Property Signatures

- **Compiler Error**:

  ```text
  The label '{label_name}' is defined with different properties. One definition of the label has 2 property declarations: '[id, code]'. Another definition has 1 property declarations: '[id]'. You need to use the same set of property declarations under the same label
  ```

- **Cause**: Two node or edge definitions share a `LABEL` (for example,
  `LABEL Entity` or `LABEL CONNECTED_TO`) and use `PROPERTIES ALL COLUMNS` on
  tables that have different columns, or declare different property sets.
- **Fix**: Either assign distinct labels to each table (`LABEL Customer`,
  `LABEL Vendor`) or explicitly list the exact common subset of properties
  (`LABEL Entity PROPERTIES (id, name, created_at)`) using column aliases
  (`col_a AS name`) so names and types match 100%.

## 4. Reference the Full Node Key, With Matching Types (`SOURCE KEY` and `DESTINATION KEY`)

- **Compiler Errors**:
  - Arity (only when the `REFERENCES` column list is omitted):

    ```text
    The number of referencing columns in the edge table does not match that of referenced columns in the node table; the former has a size of 1 but the latter has a size of 2
    ```

  - Types:

    ```text
    Data types and/or annotations of the referencing columns in the edge table do not match those of the referenced columns in the node table
    ```

- **Silent failure (no error)**: With an explicit column list, Spanner
  **accepts** a reference to a *subset* of a composite node key, for example
  `DESTINATION KEY (order_id) REFERENCES OrderNode (order_id)` where `OrderNode`
  has `KEY (customer_id, order_id)`. Each edge row then matches **every** node
  that shares that `order_id` value, so traversals return duplicated or wrong
  results.
- **Fix**:
  - Always include all composite key columns of the referenced node in
    `SOURCE KEY` / `DESTINATION KEY` and its `REFERENCES` list (for interleaved
    child nodes, that includes the parent key columns).
  - If two tables join across mismatched data types (`INT64` vs. `STRING`),
    create a SQL bridge view (`SQL SECURITY INVOKER` or `DEFINER`) that casts
    the column (`SAFE_CAST(target_id AS INT64) AS target_id_int64`) and bind the
    edge table to the view.

## 5. Explicit, Unique `KEY` Clause on SQL Bridge Views (or `validate_element_key_uniqueness`)

- **Compiler Errors**:
  - Missing key:

    ```text
    The node table '{view_name}' does not have primary key defined; graph element table keys must be explicitly defined
    ```

  - Unverifiable key (under default strict validation):

    ```text
    failed to create the graph element '{view_name}' based on view '{view_name}', because we cannot verify the specified element key (...) is unique
    ```

- **Cause**: SQL views have no physical `PRIMARY KEY`, and by default
  (`validate_element_key_uniqueness = true`) Spanner syntactically checks that
  the declared view `KEY` comes from a single table's primary key or a
  `SELECT DISTINCT` / `GROUP BY` over the key columns. A plain `UNNEST` or
  `JOIN` view without `DISTINCT` / `GROUP BY` cannot be syntactically verified.
- **Fix**: Always declare an explicit `KEY (col1, col2, ...)` on view-backed
  elements, and either:
  1. Make the view syntactically unique (pass through a single table's primary
     key unchanged, or use `SELECT DISTINCT` / `GROUP BY` over the key
     columns—required whenever raw inputs like an `ARRAY` can actually contain
     duplicate values), **or**
  2. When you have verified that the view's `KEY` is **already semantically
     unique** (such as a PK-preserving `JOIN` or `UNNEST(...) WITH OFFSET`), set
     `OPTIONS (validate_element_key_uniqueness = false)` on
     `CREATE PROPERTY GRAPH` to skip syntactic validation (ensuring no duplicate
     keys exist in data).

## 6. One Data Type per Property Name Across the Entire Graph

- **Compiler Error**:

  ```text
  The property declaration of 'id' has type conflicts. There is an existing declaration of type STRING. There is a conflicting one of type INT64
  ```

- **Cause**: The same property name is exposed with different data types
  anywhere in the graph, even under *different* labels or on a node table vs. an
  edge table (for example, `Accounts.id INT64` and `Users.id STRING`). Omitting
  `PROPERTIES` (implicit `DEFAULT LABEL PROPERTIES ALL COLUMNS`) triggers it
  whenever legacy relational tables reuse generic column names (`id`, `status`,
  `type`, `created_at`) with different types.
- **Fix**: Rename one side with an alias (`id AS user_id`), exclude it
  (`PROPERTIES ALL COLUMNS EXCEPT (id)`), or `CAST` it to the common type in
  `PROPERTIES (...)`. (Spanner tables cannot contain `STRUCT` columns, so
  struct-typed properties only arise from views.)

## 7. Every View Needs a `SQL SECURITY` Clause (`INVOKER` vs. `DEFINER`)

- **DDL Error** (raised by `CREATE VIEW`, not by the graph):
  `View '{view_name}' is missing the SQL SECURITY clause.`
- **Behavior**: `CREATE PROPERTY GRAPH` supports views defined with either
  `SQL SECURITY INVOKER` or `SQL SECURITY DEFINER`.
- **Fix**: Always include an explicit `SQL SECURITY` clause on
  `CREATE [OR REPLACE] VIEW`:
  - **`SQL SECURITY INVOKER`** (common default): Evaluates the view using the
    invoking caller's permissions on the underlying relational tables.
  - **`SQL SECURITY DEFINER`**: Evaluates the view with definer's rights—use
    when implementing row-level / fine-grained access control so users can query
    the graph view without direct privileges on the base tables.

## 8. Custom `KEY` Clause on a Table Must Contain the Primary Key or Match a Unique Index (and Avoid `NULL` Keys)

- **Compiler Error**:

  ```text
  Neither the primary keys nor any unique index defined on the property graph element source table '{table}' provides the uniqueness guarantee for graph element '{alias}' belonging to the graph '{graph}'. You want to redefine the element key columns (...) based on the source table's primary keys, or create a unique index on the element's key columns.
  ```

- **Cause**: An explicit `KEY (...)` on a table-backed node or edge that is not
  a superset of the table's primary key and has no matching `UNIQUE` index. This
  also applies to edge keys such as `KEY (src_id, dst_id, transfer_ts)` on a
  table whose primary key is `transfer_id`.
- **Silent failure (`NULL` keys)**: If a node or edge `KEY` column (from a
  nullable primary key or a `UNIQUE NULL_FILTERED` index) contains `NULL`,
  `CREATE PROPERTY GRAPH` succeeds, but `MATCH` silently skips those rows.
- **Fix**: Use the table's primary key (or a superset of it) as the element
  `KEY`, or create a `UNIQUE` index on the key columns (`UNIQUE NULL_FILTERED`
  indexes are accepted), and ensure element `KEY` columns are `NOT NULL` (or
  filtered with `IS NOT NULL` in a view).
