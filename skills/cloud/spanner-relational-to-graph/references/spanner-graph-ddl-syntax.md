# Spanner Property Graph DDL Syntax Reference

## Table of Contents

- [1. Formal Grammar (`CREATE PROPERTY GRAPH`)](#1-formal-grammar-create-property-graph):
  Lines 10-57
- [2. Syntax Rules and Clause Reference](#2-syntax-rules-and-clause-reference):
  Lines 61-152

## 1. Formal Grammar (`CREATE PROPERTY GRAPH`)

```sql
CREATE [ OR REPLACE ] PROPERTY GRAPH [ IF NOT EXISTS ] graph_name
  NODE TABLES (
    node_table_definition [, ...]
  )
  [ EDGE TABLES (
    edge_table_definition [, ...]
  ) ]
  [ OPTIONS (
    validate_element_key_uniqueness = { true | false } [, ...]
  ) ];
```

- **Strict Section Ordering**: `NODE TABLES (...)` must appear **before**
  `EDGE TABLES (...)`.

### `node_table_definition`
```sql
table_or_view_name [ AS node_table_alias ]
  [ KEY ( key_column_name [, ...] ) ]
  [ label_and_properties_list ]
  [ DYNAMIC LABEL ( label_column_name ) ]
  [ DYNAMIC PROPERTIES ( json_column_name ) ]
```

### `edge_table_definition`
```sql
table_or_view_name [ AS edge_table_alias ]
  [ KEY ( key_column_name [, ...] ) ]
  SOURCE KEY ( src_column_name [, ...] ) REFERENCES src_node_table_alias [ ( ref_column_name [, ...] ) ]
  DESTINATION KEY ( dst_column_name [, ...] ) REFERENCES dst_node_table_alias [ ( ref_column_name [, ...] ) ]
  [ label_and_properties_list ]
  [ DYNAMIC LABEL ( label_column_name ) ]
  [ DYNAMIC PROPERTIES ( json_column_name ) ]
```

### `label_and_properties_list`

```sql
{ DEFAULT LABEL | LABEL label_name }
  [ {
    NO PROPERTIES
    | PROPERTIES ( column_name [ AS property_name ] [, ...] )
    | PROPERTIES ALL COLUMNS [ EXCEPT ( column_name [, ...] ) ]
  } ]
```

---

## 2. Syntax Rules and Clause Reference

1. **`AS node_table_alias` / `AS edge_table_alias`**:
   - Every element definition has an element alias (defaults to
     `table_or_view_name` if `AS` is omitted).
   - **Global Uniqueness**: Every alias across both `NODE TABLES` and
     `EDGE TABLES` in the same property graph must be unique. When a relational
     table acts as both a node and an edge (or backs multiple edge types),
     assign distinct aliases (`Employees AS Employee`,
     `Employees AS ReportsToEdge`, `Employees AS MemberOfDeptEdge`).
2. **`KEY ( ... )`**:
   - Must uniquely identify each row in the backing table or view.
   - For base tables, always specify the full `PRIMARY KEY` column list in key
     order (including interleaved parent primary key columns).
   - For SQL bridge views (`SQL SECURITY INVOKER` or `SQL SECURITY DEFINER`,
     which lack a physical `PRIMARY KEY`), `KEY (...)` is **mandatory** and must
     specify a unique composite column tuple.
   - By default (`validate_element_key_uniqueness = true`), Spanner enforces
     uniqueness at DDL time: a table `KEY` must contain all primary key columns
     or match a `UNIQUE` index (`UNIQUE NULL_FILTERED` is accepted), and a view
     `KEY` must be syntactically provably unique (a single base table's primary
     key passed through unchanged, or `SELECT DISTINCT` / `GROUP BY` over the
     key columns). If a view's `KEY` is already semantically unique (for
     example, a PK-preserving `JOIN` without `GROUP BY`), you can disable
     syntactic view-key validation with
     `OPTIONS (validate_element_key_uniqueness = false)` on
     `CREATE PROPERTY GRAPH`—you must ensure the `KEY` columns are genuinely
     unique in data.
   - **Silent `NULL` Key Filtering**: DDL succeeds even if `KEY` columns are
     nullable, but any row where a node or edge `KEY` column (or an edge's
     `SOURCE KEY` / `DESTINATION KEY` column) is `NULL` is **silently skipped**
     by `MATCH` queries (so SQL `COUNT(*)` can exceed
     `MATCH (n) RETURN COUNT(n)`). Prefer `NOT NULL` key columns or filter
     `WHERE key_col IS NOT NULL` in views.
3. **`SOURCE KEY` and `DESTINATION KEY`**:
   - The identifier immediately following `REFERENCES` **must** match the
     **`node_table_alias`** declared in `NODE TABLES` (not the `LABEL` name and
     not the raw table name if an alias was used).
   - The number and data types of columns in `SOURCE KEY (...)` and
     `DESTINATION KEY (...)` must match the referenced node's `KEY (...)`
     1-to-1.
   - Always reference the **full** node key. If the `REFERENCES` column list is
     omitted, an arity mismatch is a compile error; but with an explicit list,
     Spanner accepts a partial key (for example,
     `REFERENCES OrderNode (order_id)` against `KEY (customer_id, order_id)`)
     and each edge then matches every node sharing that value.
4. **`LABEL`, `PROPERTIES`, `DYNAMIC LABEL`, and `DYNAMIC PROPERTIES`**:
   - On clean single-table labels without cross-table column type conflicts,
     omitting the `PROPERTIES` clause (implicit `PROPERTIES ALL COLUMNS`) is
     concise and idiomatic. Use explicit `PROPERTIES (col1 [AS alias], ...)`,
     `PROPERTIES ALL COLUMNS EXCEPT (...)`, or `NO PROPERTIES` when: (1)
     aliasing columns to resolve graph-wide property type conflicts across
     legacy tables, (2) matching identical property sets on a shared `LABEL`,
     (3) mapping dual `Table AS Node` + `Table AS Edge` or pure junction tables
     (`NO PROPERTIES` or edge-only properties), or (4) excluding
     internal/sensitive columns.
   - For schemaless tables that store runtime labels in a `STRING` column and
     dynamic attributes in a `JSON` column (a hybrid properties design), either
     use `PROPERTIES ALL COLUMNS EXCEPT (properties)` or list the static columns
     explicitly so the `JSON` column is not exposed twice:
     ```sql
     PROPERTIES (id, label, created_at)
     DYNAMIC LABEL (label)
     DYNAMIC PROPERTIES (properties)
     ```

   - Store `DYNAMIC LABEL` values in **lowercase**. A row whose label column
     holds an uppercase or mixed-case value (for example, `'Person'`) silently
     gets no dynamic label, so `MATCH (n:Person)` returns no rows for it. Labels
     in queries are case-insensitive (`:Person` matches a stored `'person'`).
     Enforce this with `CONSTRAINT label_lowercase CHECK (label = LOWER(label))`
     on the table.
   - Supported static property types include standard Spanner scalar types
     (`BOOL`, `INT64`, `FLOAT32`, `FLOAT64`, `NUMERIC`, `STRING`, `BYTES`,
     `DATE`, `TIMESTAMP`, `JSON`) and arrays of supported scalar types. (Spanner
     tables cannot contain `STRUCT` columns.)
   - A property name must have **one data type across the entire graph**, even
     under different labels or on node vs. edge tables. If two tables expose a
     same-named column with different types (for example, `id INT64` and
     `id STRING`), alias one side (`id AS user_id`) or `CAST` it; implicit
     `DEFAULT LABEL PROPERTIES ALL COLUMNS` hits this conflict too.
   - `PROPERTIES ALL COLUMNS` is expanded when the graph is created: columns
     added to the table later are not exposed until you re-run
     `CREATE OR REPLACE PROPERTY GRAPH`. Columns and tables referenced by a
     graph cannot be dropped or retyped until the graph stops referencing them.
5. **Reserved Keywords**:
   - Escape GQL / SQL reserved keywords used as identifiers or labels in
     backticks, or rename the alias/label to a non-reserved identifier
     (`OrderNode`). Verified to require escaping: `` `Order` ``, `` `Group` ``,
     `` `Contains` `` (unescaped they fail with
     `Syntax error: Unexpected keyword ...`). `User`, `Edge`, `Node`, `Path`,
     and `Graph` were accepted unescaped as aliases and labels.
