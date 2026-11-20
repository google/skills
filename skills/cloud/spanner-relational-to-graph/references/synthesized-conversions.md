# Synthesized Relational to Spanner Property Graph Conversions

## Table of Contents

- [Example 1: Multi-Tier E-Commerce Platform](#example-1-multi-tier-e-commerce-platform):
  Lines 16-162
- [Example 2: Financial AML and Transaction Network](#example-2-financial-aml-and-transaction-network):
  Lines 166-280
- [Example 3: Enterprise Organization and Project Matrix](#example-3-enterprise-organization-and-project-matrix):
  Lines 284-410
- [Example 4: Consolidated Multi-Typed Entity Schema](#example-4-consolidated-multi-typed-entity-schema):
  Lines 414-514

---

## Example 1: Multi-Tier E-Commerce Platform

### User Request (Relational Schema Input)

```sql
CREATE TABLE Customers (
  customer_id INT64 NOT NULL,
  name        STRING(100) NOT NULL,
  email       STRING(100) NOT NULL,
  country     STRING(2),
) PRIMARY KEY (customer_id);

CREATE TABLE Orders (
  customer_id INT64 NOT NULL,
  order_id    INT64 NOT NULL,
  order_date  DATE NOT NULL,
  status      STRING(20) NOT NULL,
  total_usd   NUMERIC NOT NULL,
) PRIMARY KEY (customer_id, order_id),
  INTERLEAVE IN PARENT Customers ON DELETE CASCADE;

CREATE TABLE Products (
  product_id  INT64 NOT NULL,
  sku         STRING(50) NOT NULL,
  title       STRING(200) NOT NULL,
  price       NUMERIC NOT NULL,
) PRIMARY KEY (product_id);

CREATE TABLE OrderItems (
  customer_id INT64 NOT NULL,
  order_id    INT64 NOT NULL,
  item_id     INT64 NOT NULL,
  product_id  INT64 NOT NULL,
  quantity    INT64 NOT NULL,
  unit_price  NUMERIC NOT NULL,
  CONSTRAINT FK_OrderItem_Product FOREIGN KEY (product_id) REFERENCES Products (product_id)
) PRIMARY KEY (customer_id, order_id, item_id),
  INTERLEAVE IN PARENT Orders ON DELETE CASCADE;

CREATE TABLE ProductReviews (
  review_id   INT64 NOT NULL,
  customer_id INT64 NOT NULL,
  product_id  INT64 NOT NULL,
  rating      INT64 NOT NULL,
  review_text STRING(MAX),
  review_date TIMESTAMP NOT NULL,
  CONSTRAINT FK_Review_Customer FOREIGN KEY (customer_id) REFERENCES Customers (customer_id),
  CONSTRAINT FK_Review_Product FOREIGN KEY (product_id) REFERENCES Products (product_id)
) PRIMARY KEY (review_id);
```

### 1. Graph Extension Summary & Mapping

- **Domain Decomposition & Business Purpose**: Models the e-commerce purchase
  pipeline—customers, orders, products, line items, and reviews—to enable
  recommendation and co-purchasing traversals.
- **Target Graph Scoping Decision**: 1 Unified Property Graph
  (`ECommerceGraph`).

| Relational Table | Target Graph | Graph Role | Element Alias | Graph Label | Source -> Destination | Element Key | Domain Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Customers` | `ECommerceGraph` | Node Table | `Customer` | `Customer` | N/A | `(customer_id)` | Core entity |
| `Orders` | `ECommerceGraph` | Node Table | `OrderNode` | `Order` | N/A | `(customer_id, order_id)` | Core order entity |
| `Orders` | `ECommerceGraph` | Edge Table | `PlacedOrder` | `PLACED` | `Customer -> OrderNode` | `(customer_id, order_id)` | Interleaved parent-child ownership |
| `Products` | `ECommerceGraph` | Node Table | `Product` | `Product` | N/A | `(product_id)` | Core catalog entity |
| `OrderItems` | `ECommerceGraph` | Edge Table | `ContainsProduct` | `INCLUDES_ITEM` | `OrderNode -> Product` | `(customer_id, order_id, item_id)` | Interleaved line-item relationship |
| `ProductReviews` | `ECommerceGraph` | Edge Table | `ReviewedProduct` | `REVIEWED` | `Customer -> Product` | `(review_id)` | Attributed customer-product interaction |

- **Excluded Tables**: 0 tables excluded (all 5 tables mapped).

### 2. Derived Spanner Property Graph DDL

```sql
CREATE OR REPLACE PROPERTY GRAPH ECommerceGraph
  NODE TABLES (
    Customers AS Customer
      KEY (customer_id)
      LABEL Customer PROPERTIES (customer_id, name, email, country),
    Orders AS OrderNode
      KEY (customer_id, order_id)
      LABEL `Order` PROPERTIES (customer_id, order_id, order_date, status, total_usd),
    Products AS Product
      KEY (product_id)
      LABEL Product PROPERTIES (product_id, sku, title, price)
  )
  EDGE TABLES (
    Orders AS PlacedOrder
      KEY (customer_id, order_id)
      SOURCE KEY (customer_id) REFERENCES Customer(customer_id)
      DESTINATION KEY (customer_id, order_id) REFERENCES OrderNode(customer_id, order_id)
      LABEL PLACED PROPERTIES (order_date, total_usd),
    OrderItems AS ContainsProduct
      KEY (customer_id, order_id, item_id)
      SOURCE KEY (customer_id, order_id) REFERENCES OrderNode(customer_id, order_id)
      DESTINATION KEY (product_id) REFERENCES Product(product_id)
      LABEL INCLUDES_ITEM PROPERTIES (quantity, unit_price),
    ProductReviews AS ReviewedProduct
      KEY (review_id)
      SOURCE KEY (customer_id) REFERENCES Customer(customer_id)
      DESTINATION KEY (product_id) REFERENCES Product(product_id)
      LABEL REVIEWED PROPERTIES (rating, review_text, review_date)
  );
```

### 3. Performance & Indexing Recommendations

1. **Forward Traversal Colocation**: `Orders` is interleaved in `Customers` and
   `OrderItems` is interleaved in `Orders`, colocating
   `Customer -> Order -> INCLUDES_ITEM` on the same split.
2. **Reverse Traversal Indexes**: To traverse inbound from `Product`
   (`(p:Product)<-[:INCLUDES_ITEM]-(o:Order)` or
   `(p:Product)<-[:REVIEWED]-(c:Customer)`), add covering secondary indexes:
   ```sql
   CREATE INDEX OrderItemsByProduct
   ON OrderItems (product_id, customer_id, order_id)
   STORING (quantity, unit_price);

   CREATE INDEX ReviewsByProduct
   ON ProductReviews (product_id, customer_id)
   STORING (rating, review_date);
   ```

### 4. Sample ISO GQL Queries

```sql
-- 1. Find customers who reviewed products they ordered with rating >= 4:
GRAPH ECommerceGraph
MATCH (c:Customer)-[:PLACED]->(o:`Order`)-[:INCLUDES_ITEM]->(p:Product)<-[r:REVIEWED]-(c)
WHERE r.rating >= 4 AND o.total_usd > 200
RETURN c.name AS customer_name, p.title AS product_title, r.rating, o.total_usd;

-- 2. Frequently bought together co-occurrence recommendation:
GRAPH ECommerceGraph
MATCH (p1:Product {product_id: 101})<-[:INCLUDES_ITEM]-(o:`Order`)-[:INCLUDES_ITEM]->(p2:Product)
WHERE p2.product_id != 101
RETURN p2.title AS recommended_product, COUNT(o) AS co_occurrence_count
GROUP BY p2.title
ORDER BY co_occurrence_count DESC
LIMIT 5;
```

### 5. Schema Verification Status

- **Verification Target**: Spanner Emulator
  (`gcloud spanner databases create --ddl-file=...`)
- **Status**: `PASSED` (Composite keys on interleaved `Orders` and `OrderItems`
  aligned; reserved identifier `` `Order` `` escaped).

---

## Example 2: Financial AML and Transaction Network

### User Request (Relational Schema Input)

```sql
CREATE TABLE FinancialEntities (
  entity_id    INT64 NOT NULL,
  entity_type  STRING(30) NOT NULL,
  legal_name   STRING(150) NOT NULL,
  jurisdiction STRING(50),
) PRIMARY KEY (entity_id);

CREATE TABLE BankAccounts (
  account_id  INT64 NOT NULL,
  entity_id   INT64 NOT NULL,
  iban        STRING(34) NOT NULL,
  currency    STRING(3) NOT NULL,
  balance     NUMERIC NOT NULL,
  is_flagged  BOOL NOT NULL,
  CONSTRAINT FK_Account_Entity FOREIGN KEY (entity_id) REFERENCES FinancialEntities (entity_id)
) PRIMARY KEY (account_id);

CREATE TABLE WireTransfers (
  transfer_id    INT64 NOT NULL,
  src_account_id INT64 NOT NULL,
  dst_account_id INT64 NOT NULL,
  amount         NUMERIC NOT NULL,
  transfer_time  TIMESTAMP NOT NULL,
  audit_score    FLOAT64,
  CONSTRAINT FK_Transfer_Src FOREIGN KEY (src_account_id) REFERENCES BankAccounts (account_id),
  CONSTRAINT FK_Transfer_Dst FOREIGN KEY (dst_account_id) REFERENCES BankAccounts (account_id)
) PRIMARY KEY (transfer_id);
```

### 1. Graph Extension Summary & Mapping

- **Domain Decomposition & Business Purpose**: Models financial entities, bank
  accounts, and wire transfers for anti-money laundering (AML) cycle detection
  and multi-hop fund tracing.
- **Target Graph Scoping Decision**: 1 Unified Property Graph (`FinCrimeGraph`).

| Relational Table | Target Graph | Graph Role | Element Alias | Graph Label | Source -> Destination | Element Key | Domain Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `FinancialEntities` | `FinCrimeGraph` | Node Table | `Entity` | `Entity` | N/A | `(entity_id)` | Core legal entity |
| `BankAccounts` | `FinCrimeGraph` | Node Table | `Account` | `Account` | N/A | `(account_id)` | Core account node |
| `BankAccounts` | `FinCrimeGraph` | Edge Table | `EntityOwnsAccount` | `OWNS` | `Entity -> Account` | `(account_id)` | 1:N ownership via FK |
| `WireTransfers` | `FinCrimeGraph` | Edge Table | `AccountTransfers` | `TRANSFERRED_TO` | `Account -> Account` | `(transfer_id)` | Directed transaction edge |

- **Excluded Tables**: 0 tables excluded.

### 2. Derived Spanner Property Graph DDL

```sql
CREATE OR REPLACE PROPERTY GRAPH FinCrimeGraph
  NODE TABLES (
    FinancialEntities AS Entity
      KEY (entity_id)
      LABEL Entity PROPERTIES (entity_id, entity_type, legal_name, jurisdiction),
    BankAccounts AS Account
      KEY (account_id)
      LABEL Account PROPERTIES (account_id, iban, currency, balance, is_flagged)
  )
  EDGE TABLES (
    BankAccounts AS EntityOwnsAccount
      KEY (account_id)
      SOURCE KEY (entity_id) REFERENCES Entity(entity_id)
      DESTINATION KEY (account_id) REFERENCES Account(account_id)
      LABEL OWNS NO PROPERTIES,
    WireTransfers AS AccountTransfers
      KEY (transfer_id)
      SOURCE KEY (src_account_id) REFERENCES Account(account_id)
      DESTINATION KEY (dst_account_id) REFERENCES Account(account_id)
      LABEL TRANSFERRED_TO PROPERTIES (amount, transfer_time, audit_score)
  );
```

### 3. Performance & Indexing Recommendations

1. **Outbound and Inbound Transfer Indexes**: Because `WireTransfers` uses a
   synthetic single-column key `(transfer_id)`, add secondary indexes for both
   forward (`src_account_id`) and reverse (`dst_account_id`) traversals:
   ```sql
   CREATE INDEX WireTransfersBySrcDst
   ON WireTransfers (src_account_id, dst_account_id, transfer_time)
   STORING (amount, audit_score);

   CREATE INDEX WireTransfersByDstSrc
   ON WireTransfers (dst_account_id, src_account_id, transfer_time)
   STORING (amount, audit_score);
   ```

2. **Same-Node-Type Edge Trade-Off**: Keeping `WireTransfers` as a standalone
   table allows bidirectional `ON DELETE CASCADE` foreign keys on both
   `src_account_id` and `dst_account_id` so deleting an account cleans up both
   incoming and outgoing transfers.

### 4. Sample ISO GQL Queries

```sql
-- 1. Detect circular funds routing (cycles of 2 to 4 hops):
GRAPH FinCrimeGraph
MATCH (a:Account {account_id: @acct_id})-[t:TRANSFERRED_TO]->{2, 4}(a:Account)
RETURN a.iban AS account_iban, ARRAY_LENGTH(t) AS cycle_depth;

-- 2. Trace funds from high-risk jurisdictions to flagged accounts:
GRAPH FinCrimeGraph
MATCH (e:Entity)-[:OWNS]->(src:Account)-[t:TRANSFERRED_TO]->{1, 3}(dst:Account)
WHERE e.jurisdiction IN ('HIGH_RISK_A', 'HIGH_RISK_B') AND dst.is_flagged = TRUE
RETURN e.legal_name, src.iban AS src_iban, dst.iban AS dst_iban, ARRAY_LENGTH(t) AS hops;
```

### 5. Schema Verification Status

- **Verification Target**: Spanner Emulator
- **Status**: `PASSED`

---

## Example 3: Enterprise Organization and Project Matrix

### User Request (Relational Schema Input)

```sql
CREATE TABLE Departments (
  dept_id     INT64 NOT NULL,
  dept_name   STRING(100) NOT NULL,
  cost_center STRING(20),
) PRIMARY KEY (dept_id);

CREATE TABLE Employees (
  emp_id     INT64 NOT NULL,
  full_name  STRING(100) NOT NULL,
  job_title  STRING(100) NOT NULL,
  dept_id    INT64 NOT NULL,
  manager_id INT64,
  CONSTRAINT FK_Emp_Dept FOREIGN KEY (dept_id) REFERENCES Departments (dept_id),
  CONSTRAINT FK_Emp_Mgr FOREIGN KEY (manager_id) REFERENCES Employees (emp_id)
) PRIMARY KEY (emp_id);

CREATE TABLE Projects (
  project_id   INT64 NOT NULL,
  project_code STRING(50) NOT NULL,
  budget       NUMERIC,
) PRIMARY KEY (project_id);

CREATE TABLE ProjectAssignments (
  emp_id     INT64 NOT NULL,
  project_id INT64 NOT NULL,
  role_name  STRING(50) NOT NULL,
  allocation NUMERIC NOT NULL,
  CONSTRAINT FK_Assign_Emp FOREIGN KEY (emp_id) REFERENCES Employees (emp_id),
  CONSTRAINT FK_Assign_Proj FOREIGN KEY (project_id) REFERENCES Projects (project_id)
) PRIMARY KEY (emp_id, project_id);
```

### 1. Graph Extension Summary & Mapping

- **Domain Decomposition & Business Purpose**: Models organizational reporting
  hierarchies, department membership, and M:N project staffing.
- **Target Graph Scoping Decision**: 1 Unified Property Graph
  (`EnterpriseOrgGraph`).

| Relational Table | Target Graph | Graph Role | Element Alias | Graph Label | Source -> Destination | Element Key | Domain Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Departments` | `EnterpriseOrgGraph` | Node Table | `Department` | `Department` | N/A | `(dept_id)` | Core org unit |
| `Employees` | `EnterpriseOrgGraph` | Node Table | `Employee` | `Employee` | N/A | `(emp_id)` | Core person entity |
| `Projects` | `EnterpriseOrgGraph` | Node Table | `Project` | `Project` | N/A | `(project_id)` | Core workstream |
| `Employees` | `EnterpriseOrgGraph` | Edge Table | `ReportsToEdge` | `REPORTS_TO` | `Employee -> Employee` | `(emp_id)` | Self-referential hierarchy |
| `Employees` | `EnterpriseOrgGraph` | Edge Table | `MemberOfDeptEdge` | `MEMBER_OF` | `Employee -> Department` | `(emp_id)` | 1:N department membership |
| `ProjectAssignments` | `EnterpriseOrgGraph` | Edge Table | `AssignedToProject` | `ASSIGNED_TO` | `Employee -> Project` | `(emp_id, project_id)` | Attributed M:N junction |

- **Excluded Tables**: 0 tables excluded.

### 2. Derived Spanner Property Graph DDL

```sql
CREATE OR REPLACE PROPERTY GRAPH EnterpriseOrgGraph
  NODE TABLES (
    Departments AS Department
      KEY (dept_id)
      LABEL Department PROPERTIES (dept_id, dept_name, cost_center),
    Employees AS Employee
      KEY (emp_id)
      LABEL Employee PROPERTIES (emp_id, full_name, job_title),
    Projects AS Project
      KEY (project_id)
      LABEL Project PROPERTIES (project_id, project_code, budget)
  )
  EDGE TABLES (
    Employees AS ReportsToEdge
      KEY (emp_id)
      SOURCE KEY (emp_id) REFERENCES Employee(emp_id)
      DESTINATION KEY (manager_id) REFERENCES Employee(emp_id)
      LABEL REPORTS_TO NO PROPERTIES,
    Employees AS MemberOfDeptEdge
      KEY (emp_id)
      SOURCE KEY (emp_id) REFERENCES Employee(emp_id)
      DESTINATION KEY (dept_id) REFERENCES Department(dept_id)
      LABEL MEMBER_OF NO PROPERTIES,
    ProjectAssignments AS AssignedToProject
      KEY (emp_id, project_id)
      SOURCE KEY (emp_id) REFERENCES Employee(emp_id)
      DESTINATION KEY (project_id) REFERENCES Project(project_id)
      LABEL ASSIGNED_TO PROPERTIES (role_name, allocation)
  );
```

### 3. Performance & Indexing Recommendations

1. **Reverse Staffing Lookup Index**: To find all employees assigned to a given
   project (`(p:Project)<-[:ASSIGNED_TO]-(e:Employee)`):
   ```sql
   CREATE INDEX StaffingByProject
   ON ProjectAssignments (project_id, emp_id)
   STORING (role_name, allocation);
   ```

2. **Direct-Reports Lookup Index**: To traverse downward from a manager to
   direct reports (`(mgr:Employee)<-[:REPORTS_TO]-(report:Employee)`):
   ```sql
   CREATE INDEX EmployeesByManager
   ON Employees (manager_id, emp_id)
   STORING (full_name, job_title);
   ```

### 4. Sample ISO GQL Queries

```sql
-- 1. Traverse management chain up to 5 levels deep:
GRAPH EnterpriseOrgGraph
MATCH (e:Employee)-[r:REPORTS_TO]->{1, 5}(mgr:Employee)
WHERE mgr.job_title = 'VP of Engineering'
RETURN e.full_name AS employee_name, mgr.full_name AS executive_name, ARRAY_LENGTH(r) AS depth;

-- 2. Find cross-department project collaborations:
GRAPH EnterpriseOrgGraph
MATCH (d1:Department)<-[:MEMBER_OF]-(e1:Employee)-[:ASSIGNED_TO]->(p:Project)<-[:ASSIGNED_TO]-(e2:Employee)-[:MEMBER_OF]->(d2:Department)
WHERE d1.dept_id < d2.dept_id
RETURN p.project_code, d1.dept_name AS dept_1, e1.full_name AS emp_1, d2.dept_name AS dept_2, e2.full_name AS emp_2;
```

### 5. Schema Verification Status

- **Verification Target**: Spanner Emulator
- **Status**: `PASSED`

---

## Example 4: Consolidated Multi-Typed Entity Schema

### User Request (Relational Schema Input)

```sql
CREATE TABLE Entities (
  entity_type      STRING(50) NOT NULL,
  entity_id        STRING(100) NOT NULL,
  display_name     STRING(200),
  confidence_score FLOAT64,
  created_at       TIMESTAMP
) PRIMARY KEY (entity_type, entity_id);

CREATE TABLE EntityAssociations (
  source_type   STRING(50) NOT NULL,
  source_id     STRING(100) NOT NULL,
  target_type   STRING(50) NOT NULL,
  target_id     STRING(100) NOT NULL,
  relation_verb STRING(50) NOT NULL,
  first_seen    TIMESTAMP,
  CONSTRAINT FK_Source FOREIGN KEY (source_type, source_id) REFERENCES Entities (entity_type, entity_id),
  CONSTRAINT FK_Target FOREIGN KEY (target_type, target_id) REFERENCES Entities (entity_type, entity_id)
) PRIMARY KEY (source_type, source_id, target_type, target_id, relation_verb);

CREATE TABLE Labels (
  label_id STRING(50) NOT NULL,
  category STRING(50)
) PRIMARY KEY (label_id);

CREATE TABLE EntityLabels (
  entity_type STRING(50) NOT NULL,
  entity_id   STRING(100) NOT NULL,
  label_id    STRING(50) NOT NULL,
  CONSTRAINT FK_Entity FOREIGN KEY (entity_type, entity_id) REFERENCES Entities (entity_type, entity_id),
  CONSTRAINT FK_Label FOREIGN KEY (label_id) REFERENCES Labels (label_id)
) PRIMARY KEY (entity_type, entity_id, label_id);
```

### 1. Graph Extension Summary & Mapping

- **Consolidated Entity Strategy**: Maps the composite-keyed
  `Entities(entity_type, entity_id)` table to a unified `Entity` node table with
  `entity_type` exposed as a filterable property.

| Relational Table | Target Graph | Graph Role | Element Alias | Graph Label | Source -> Destination | Element Key |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Entities` | `ThreatIntelGraph` | Node Table | `Entity` | `Entity` | N/A | `(entity_type, entity_id)` |
| `Labels` | `ThreatIntelGraph` | Node Table | `LabelNode` | `Label` | N/A | `(label_id)` |
| `EntityAssociations` | `ThreatIntelGraph` | Edge Table | `AssociatedWithEdge` | `ASSOCIATED_WITH` | `Entity -> Entity` | `(source_type, source_id, target_type, target_id, relation_verb)` |
| `EntityLabels` | `ThreatIntelGraph` | Edge Table | `HasLabelEdge` | `HAS_LABEL` | `Entity -> LabelNode` | `(entity_type, entity_id, label_id)` |

### 2. Derived Spanner Property Graph DDL

```sql
CREATE OR REPLACE PROPERTY GRAPH ThreatIntelGraph
  NODE TABLES (
    Entities AS Entity
      KEY (entity_type, entity_id)
      LABEL Entity PROPERTIES (entity_type, entity_id, display_name, confidence_score, created_at),
    Labels AS LabelNode
      KEY (label_id)
      LABEL Label PROPERTIES (label_id, category)
  )
  EDGE TABLES (
    EntityAssociations AS AssociatedWithEdge
      KEY (source_type, source_id, target_type, target_id, relation_verb)
      SOURCE KEY (source_type, source_id) REFERENCES Entity(entity_type, entity_id)
      DESTINATION KEY (target_type, target_id) REFERENCES Entity(entity_type, entity_id)
      LABEL ASSOCIATED_WITH PROPERTIES (relation_verb, first_seen),
    EntityLabels AS HasLabelEdge
      KEY (entity_type, entity_id, label_id)
      SOURCE KEY (entity_type, entity_id) REFERENCES Entity(entity_type, entity_id)
      DESTINATION KEY (label_id) REFERENCES LabelNode(label_id)
      LABEL HAS_LABEL NO PROPERTIES
  );
```

### 3. Performance & Indexing Recommendations

```sql
CREATE INDEX IdxEntityAssocReverse
ON EntityAssociations (target_type, target_id, source_type, source_id, relation_verb)
STORING (first_seen);

CREATE INDEX IdxEntityLabelsReverse
ON EntityLabels (label_id, entity_type, entity_id);
```

### 4. Sample ISO GQL Queries

```sql
GRAPH ThreatIntelGraph
MATCH (m1:Entity {entity_type: 'MALWARE'})-[:ASSOCIATED_WITH]->(infra:Entity)<-[:ASSOCIATED_WITH]-(m2:Entity {entity_type: 'MALWARE'})
WHERE m1.entity_id < m2.entity_id
RETURN m1.display_name AS malware_1, m2.display_name AS malware_2, infra.display_name AS shared_c2;
```

### 5. Schema Verification Status

- **Verification Target**: Spanner Emulator
- **Status**: `PASSED`
