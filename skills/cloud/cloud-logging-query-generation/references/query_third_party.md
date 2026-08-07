# Third-party application LQL queries

## Table of contents

- [Example queries](#example-queries) (L31-L247)
- [Apache logs](#apache-logs) (L33-L40)
- [Cassandra logs](#cassandra-logs) (L42-L49)
- [Chef logs](#chef-logs) (L51-L58)
- [Gitlab logs](#gitlab-logs) (L60-L67)
- [Jenkins logs](#jenkins-logs) (L69-L76)
- [Jetty logs](#jetty-logs) (L78-L85)
- [Joomla logs](#joomla-logs) (L87-L94)
- [Linux syslogs](#linux-syslogs) (L96-L103)
- [Magneto logs](#magneto-logs) (L105-L112)
- [Mediawiki logs](#mediawiki-logs) (L114-L121)
- [memcached logs](#memcached-logs) (L123-L130)
- [MongoDB logs](#mongodb-logs) (L132-L139)
- [MySQL logs](#mysql-logs) (L141-L148)
- [Nginx logs](#nginx-logs) (L150-L157)
- [PostgreSQL logs](#postgresql-logs) (L159-L166)
- [Puppet logs](#puppet-logs) (L168-L175)
- [RabbitMQ logs](#rabbitmq-logs) (L177-L184)
- [Redmine logs](#redmine-logs) (L186-L193)
- [Salt logs](#salt-logs) (L195-L202)
- [Slow MySQL queries](#slow-mysql-queries) (L204-L211)
- [Solr logs](#solr-logs) (L213-L220)
- [SugarCRM logs](#sugarcrm-logs) (L222-L229)
- [Tomcat logs](#tomcat-logs) (L231-L238)
- [Zookeeper logs](#zookeeper-logs) (L240-L247)

## Example queries

### Apache logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
(logName:"/apache-access" OR logName:"/apache-error")
```

### Cassandra logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("cassandra")
```

### Chef logs

**Variables to replace:** `<PROJECT_ID>`

```lql
resource.type="gce_instance" AND
logName:"projects/<PROJECT_ID>/logs/chef-"
```

### Gitlab logs

**Variables to replace:** `<PROJECT_ID>`

```lql
resource.type="gce_instance" AND
logName:"projects/<PROJECT_ID>/logs/gitlab-"
```

### Jenkins logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("jenkins")
```

### Jetty logs

**Variables to replace:** `<PROJECT_ID>`

```lql
resource.type="gce_instance" AND
logName:"projects/<PROJECT_ID>/logs/jetty-"
```

### Joomla logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("joomla")
```

### Linux syslogs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("syslog")
```

### Magneto logs

**Variables to replace:** `<PROJECT_ID>`

```lql
resource.type="gce_instance" AND
logName:"projects/<PROJECT_ID>/logs/magneto-"
```

### Mediawiki logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("mediawiki")
```

### memcached logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("memcached")
```

### MongoDB logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("mongodb")
```

### MySQL logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("mysql")
```

### Nginx logs

**Variables to replace:** `<PROJECT_ID>`

```lql
resource.type="gce_instance" AND
logName:"projects/<PROJECT_ID>/logs/nginx-"
```

### PostgreSQL logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("postgresql")
```

### Puppet logs

**Variables to replace:** `<PROJECT_ID>`

```lql
resource.type="gce_instance" AND
logName:"projects/<PROJECT_ID>/logs/puppet-"
```

### RabbitMQ logs

**Variables to replace:** `<PROJECT_ID>`

```lql
resource.type="gce_instance" AND
logName:"projects/<PROJECT_ID>/logs/rabbitmq-"
```

### Redmine logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("redmine")
```

### Salt logs

**Variables to replace:** `<PROJECT_ID>`

```lql
resource.type="gce_instance" AND
logName:"projects/<PROJECT_ID>/logs/salt-"
```

### Slow MySQL queries

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("mysql-slow")
```

### Solr logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("solr")
```

### SugarCRM logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("sugarcrm")
```

### Tomcat logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("tomcat")
```

### Zookeeper logs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("zookeeper")
```
