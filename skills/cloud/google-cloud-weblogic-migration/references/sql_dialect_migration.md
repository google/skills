# Oracle & PointBase SQL Dialect to Standard ANSI SQL Translation Guide

Legacy WebLogic monoliths almost universally ran on Oracle Database in
production (or PointBase for local development and testing). When migrating to
cloud-native managed databases on GCP (Google Cloud SQL for PostgreSQL/MySQL or
Google Cloud AlloyDB), vendor-specific SQL syntax embedded in JPA native
queries, JDBC `PreparedStatement` strings, or CMP finder expressions must be
translated to standard ANSI SQL.

## Table of Contents

*   [1. Oracle Specific Outer Joins ((+))](#1-oracle-specific-outer-joins) (Line 20)
*   [2. Specific SQL Functions & Null Handling](#2-specific-sql-functions--null-handling) (Line 57)
*   [3. Sequences and SELECT ... FROM DUAL](#3-sequences-and-select--from-dual) (Line 87)
*   [4. Oracle Hierarchical Queries (CONNECT BY PRIOR)](#4-oracle-hierarchical-queries-connect-by-prior) (Line 120)
*   [5. Dialect Configuration in Framework Persistence Layers](#5-dialect-configuration-in-framework-persistence-layers) (Line 155)

--------------------------------------------------------------------------------

## 1. Oracle Specific Outer Joins (`(+)`)

In legacy Oracle SQL, outer joins were written using the oracle `(+)` operator
instead of ANSI `LEFT OUTER JOIN` or `RIGHT OUTER JOIN`.

### Before: Legacy Oracle Outer Join Syntax

```sql
-- Oracle Specific Left Outer Join
SELECT p.patient_id, p.name, a.city, a.state
FROM patient_table p, address_table a
WHERE p.address_id = a.address_id(+)
  AND p.status = 'ACTIVE';

-- Oracle Specific Right Outer Join
SELECT d.dept_name, e.emp_id, e.emp_name
FROM department_table d, employee_table e
WHERE d.dept_id(+) = e.dept_id;
```

### After: Standard ANSI SQL (Cloud SQL / AlloyDB Compatible)

```sql
-- Standard ANSI Left Outer Join
SELECT p.patient_id, p.name, a.city, a.state
FROM patient_table p
LEFT OUTER JOIN address_table a ON p.address_id = a.address_id
WHERE p.status = 'ACTIVE';

-- Standard ANSI Right Outer Join
SELECT d.dept_name, e.emp_id, e.emp_name
FROM employee_table e
LEFT OUTER JOIN department_table d ON e.dept_id = d.dept_id;
```

--------------------------------------------------------------------------------

## 2. Specific SQL Functions & Null Handling

Oracle and PointBase provide oracle specific scalar functions that fail when
executed on PostgreSQL or MySQL.

| Legacy Oracle /         | Standard ANSI SQL /     | Description              |
: PointBase Function      : PostgreSQL Equivalent   :                          :
| :---------------------- | :---------------------- | :----------------------- |
| `NVL(col, default_val)` | `COALESCE(col,          | Returns `default_val` if |
:                         : default_val)`           : `col` is NULL.           :
| `DECODE(col, v1, r1,    | `CASE WHEN col = v1     | Inline conditional       |
: v2, r2, def)`           : THEN r1 WHEN col = v2   : branch / switch          :
:                         : THEN r2 ELSE def END`   : statement.               :
| `SYSDATE`               | `CURRENT_TIMESTAMP` (or | Returns current system   |
:                         : `NOW()`)                : date and time.           :
| `TO_DATE('2026-07-06',  | `TO_DATE('2026-07-06',  | Date string parsing      |
: 'YYYY-MM-DD')`          : 'YYYY-MM-DD')` or       : (PostgreSQL supports     :
:                         : `'2026-07-06'\:\:date`  : standard casting).       :
| `TRUNC(SYSDATE)`        | `CURRENT_DATE` (or      | Strips time component    |
:                         : `DATE_TRUNC('day',      : from timestamp.          :
:                         : CURRENT_TIMESTAMP)`)    :                          :
| `INSTR(str, substr)`    | `POSITION(substr IN     | Returns 1-based index of |
:                         : str)`                   : substring in string.     :
| `SUBSTR(str, start,     | `SUBSTRING(str FROM     | Substring extraction.    |
: len)`                   : start FOR len)`         :                          :
| `ROWNUM <= 10`          | `LIMIT 10` (at end of   | Limits row count         |
:                         : query)                  : returned by query.       :

--------------------------------------------------------------------------------

## 3. Sequences and `SELECT ... FROM DUAL`

Oracle requires selecting from a dummy table named `DUAL` to evaluate
expressions or fetch sequence generators.

### Before: Legacy Oracle Sequence & DUAL

```sql
-- Fetching sequence in Oracle
SELECT PATIENT_SEQ.NEXTVAL FROM DUAL;

-- Evaluating constant expression in Oracle
SELECT 'PING' AS status FROM DUAL;
```

### After: Cloud SQL / AlloyDB (PostgreSQL / MySQL)

```sql
-- PostgreSQL: Fetching sequence (DUAL is unnecessary)
SELECT nextval('patient_seq');

-- PostgreSQL / MySQL: Evaluating constant expression without FROM clause
SELECT 'PING' AS status;

-- Modern Schema Best Practice: Replace sequence lookups with IDENTITY / SERIAL columns in DDL
CREATE TABLE patient_table (
    patient_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);
```

--------------------------------------------------------------------------------

## 4. Oracle Hierarchical Queries (`CONNECT BY PRIOR`)

Legacy Oracle SQL supports tree traversal using `CONNECT BY PRIOR` and `START
WITH`.

### Before: Legacy Oracle Hierarchical Query

```sql
SELECT emp_id, emp_name, manager_id
FROM employee_table
START WITH manager_id IS NULL
CONNECT BY PRIOR emp_id = manager_id;
```

### After: Standard ANSI Recursive Common Table Expressions (CTE)

```sql
WITH RECURSIVE org_chart AS (
    -- Base case: Top-level managers
    SELECT emp_id, emp_name, manager_id, 1 AS level
    FROM employee_table
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive step: Employees reporting to managers in org_chart
    SELECT e.emp_id, e.emp_name, e.manager_id, o.level + 1
    FROM employee_table e
    INNER JOIN org_chart o ON e.manager_id = o.emp_id
)
SELECT emp_id, emp_name, manager_id FROM org_chart;
```

--------------------------------------------------------------------------------

## 5. Dialect Configuration in Framework Persistence Layers

When refactoring Spring Boot or Quarkus microservices, ensure the JPA /
Hibernate database dialect property is explicitly updated to match the target
cloud managed database:

### Spring Boot (`application.properties`)

```properties
# Cloud SQL / AlloyDB PostgreSQL Dialect
spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect
spring.jpa.hibernate.ddl-auto=validate

# Or for Cloud SQL MySQL
# spring.jpa.database-platform=org.hibernate.dialect.MySQLDialect
```

### Quarkus (`application.properties`)

```properties
# Quarkus automatically infers dialect from db-kind, but can be explicitly set
quarkus.datasource.db-kind=postgresql
quarkus.hibernate-orm.dialect=org.hibernate.dialect.PostgreSQLDialect
```
