# Example: EJB Stateless Session Bean Migration

This example shows how to migrate a Stateless Session Bean (EJB) that uses
Container-Managed Transactions (CMT) and JNDI lookups to both Spring Boot and
Quarkus.

## 1. Legacy WebLogic EJB (Before)

### Remote Interface

```java
package com.example.legacy;

import javax.ejb.Remote;

@Remote
public interface CatalogService {
    public Product getProduct(String id);
    public void addProduct(Product product);
}
```

### Bean Implementation

```java
package com.example.legacy;

import javax.ejb.Stateless;
import javax.ejb.TransactionAttribute;
import javax.ejb.TransactionAttributeType;
import javax.naming.InitialContext;
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

@Stateless(name = "CatalogService")
public class CatalogServiceBean implements CatalogService {

    // JNDI Lookup for Datasource (Legacy way)
    private Connection getConnection() throws Exception {
        InitialContext ctx = new InitialContext();
        DataSource ds = (DataSource) ctx.lookup("jdbc/CatalogDS");
        return ds.getConnection();
    }

    public Product getProduct(String id) {
        try (Connection conn = getConnection();
             PreparedStatement ps = conn.prepareStatement("SELECT name, price FROM products WHERE id = ?")) {
            ps.setString(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return new Product(id, rs.getString("name"), rs.getDouble("price"));
                }
            }
        } catch (Exception e) {
            throw new RuntimeException("Database error", e);
        }
        return null;
    }

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void addProduct(Product product) {
        try (Connection conn = getConnection();
             PreparedStatement ps = conn.prepareStatement("INSERT INTO products (id, name, price) VALUES (?, ?, ?)")) {
            ps.setString(1, product.getId());
            ps.setString(2, product.getName());
            ps.setDouble(3, product.getPrice());
            ps.executeUpdate();
        } catch (Exception e) {
            throw new RuntimeException("Transaction failed", e);
        }
    }
}
```

--------------------------------------------------------------------------------

## 2. Spring Boot Migration (After)

In Spring Boot, we use `@Service` for the bean, `@Autowired` for dependency
injection (though Spring Boot configures the `DataSource` bean automatically),
and Spring JDBC (or JPA) to simplify database access.

### Spring Service

```java
package com.example.modern;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

@Service
public class CatalogServiceImpl implements CatalogService {

    // Spring injects the Datasource automatically based on application.properties
    @Autowired
    private DataSource dataSource;

    @Override
    public Product getProduct(String id) {
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement("SELECT name, price FROM products WHERE id = ?")) {
            ps.setString(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return new Product(id, rs.getString("name"), rs.getDouble("price"));
                }
            }
        } catch (Exception e) {
            throw new RuntimeException("Database error", e);
        }
        return null;
    }

    @Override
    @Transactional // Spring transaction management
    public void addProduct(Product product) {
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement("INSERT INTO products (id, name, price) VALUES (?, ?, ?)")) {
            ps.setString(1, product.getId());
            ps.setString(2, product.getName());
            ps.setDouble(3, product.getPrice());
            ps.executeUpdate();
        } catch (Exception e) {
            throw new RuntimeException("Transaction failed", e);
        }
    }
}
```

--------------------------------------------------------------------------------

## 3. Quarkus Migration (After)

In Quarkus, we use CDI `@ApplicationScoped` and Jakarta Transactions
`@Transactional`.

### Quarkus CDI Bean

```java
package com.example.modern;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

@ApplicationScoped
public class CatalogServiceBean implements CatalogService {

    // CDI injects the Datasource automatically
    @Inject
    DataSource dataSource;

    @Override
    public Product getProduct(String id) {
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement("SELECT name, price FROM products WHERE id = ?")) {
            ps.setString(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return new Product(id, rs.getString("name"), rs.getDouble("price"));
                }
            }
        } catch (Exception e) {
            throw new RuntimeException("Database error", e);
        }
        return null;
    }

    @Override
    @Transactional(Transactional.TxType.REQUIRED) // Jakarta transaction
    public void addProduct(Product product) {
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement("INSERT INTO products (id, name, price) VALUES (?, ?, ?)")) {
            ps.setString(1, product.getId());
            ps.setString(2, product.getName());
            ps.setDouble(3, product.getPrice());
            ps.executeUpdate();
        } catch (Exception e) {
            throw new RuntimeException("Transaction failed", e);
        }
    }
}
```
