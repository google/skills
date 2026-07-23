# Ops Agent references for third-party app logging

Use these upstream `ops-agent` sources to reproduce an app's log parsing in GBOC.
All links point at `master`; pin to a release tag if you need reproducibility.

## How to fetch (avoid truncation)

`read_url_content` truncates long files. Prefer `curl` on the raw host and grep:

```bash
# App definition (receiver types, regex, TimeFormat, severity mapping)
curl -sSL https://raw.githubusercontent.com/GoogleCloudPlatform/ops-agent/master/apps/<app>.go

# Shared access-log parser (apache/nginx/jetty/tomcat/couchbase/iis access logs)
curl -sSL https://raw.githubusercontent.com/GoogleCloudPlatform/ops-agent/master/apps/common_logging_processors.go

# OTel golden output (only some apps): the exact transform + field layout
curl -sSL https://raw.githubusercontent.com/GoogleCloudPlatform/ops-agent/master/confgenerator/testdata/goldens/logging-otel-receiver_<app>/golden/linux/otel.yaml
```

- App source: `https://github.com/GoogleCloudPlatform/ops-agent/blob/master/apps/<app>.go`
- Golden dir: `https://github.com/GoogleCloudPlatform/ops-agent/tree/master/confgenerator/testdata/goldens/logging-otel-receiver_<app>`

## Apps with a logging parser

Derived from the ops-agent `apps/` directory (files defining a logging
processor/receiver). "OTel golden" marks apps that also have a
`logging-otel-receiver_<app>` golden — the most complete reference. For the
others, read `apps/<app>.go` (and `common_logging_processors.go` for access
logs) to extract the regex, timestamp, and severity mapping. Receiver-type names
below are indicative; always confirm the exact names in the source.

| App | Indicative receiver types | Source (`apps/`) | OTel golden |
| --- | --- | --- | --- |
| nginx | `nginx_access`, `nginx_error` | `nginx.go` | ✅ `logging-otel-receiver_nginx` |
| mysql | `mysql_error`, `mysql_general`, `mysql_slow` | `mysql.go` | ✅ `logging-otel-receiver_mysql` |
| mongodb | `mongodb` | `mongodb.go` | ✅ `logging-otel-receiver_mongodb` |
| kafka | `kafka` | `kafka.go` | ✅ `logging-otel-receiver_kafka` |
| apache | `apache_access`, `apache_error` | `apache.go` | — |
| iis | `iis_access` | `iis.go` | — |
| jetty | `jetty_access` | `jetty.go` | — |
| tomcat | `tomcat_access`, `tomcat_system` | `tomcat.go` | — |
| couchbase | `couchbase_general`, `couchbase_http_access` | `couchbase.go` | — |
| couchdb | `couchdb` | `couchdb.go` | — |
| elasticsearch | `elasticsearch_json`, `elasticsearch_gc` | `elasticsearch.go` | — |
| postgresql | `postgresql_general` | `postgresql.go` | — |
| oracledb | `oracledb_audit`, `oracledb_alert` | `oracledb.go` | — |
| vault | `vault_audit` | `vault.go` | — |
| zookeeper | `zookeeper_general` | `zookeeper.go` | — |
| cassandra | `cassandra_system`, `cassandra_debug`, `cassandra_gc` | `cassandra.go` | — |
| hadoop | `hadoop` | `hadoop.go` | — |
| hbase | `hbase` | `hbase.go` | — |
| flink | `flink` | `flink.go` | — |
| solr | `solr_system` | `solr.go` | — |
| rabbitmq | `rabbitmq` | `rabbitmq.go` | — |
| redis | `redis` | `redis.go` | — |
| saphana | `saphana` | `saphana.go` | — |
| varnish | `varnishlog` | `varnish.go` | — |
| wildfly | `wildfly` | `wildfly.go` | — |
| active_directory_ds | `active_directory_ds` (Windows event log) | `active_directory_ds.go` | — |

> The shared access-log parser used by apache/nginx/jetty/tomcat/couchbase/iis
> lives in `apps/common_logging_processors.go` (`genericAccessLogParser`).

## Generic / infrastructure log references

These goldens are useful patterns even outside a specific app:

- `logging-otel-receiver_systemd` — journald / systemd.
- `logging-otel-receiver_syslog_type_multiple_receivers` — syslog (tcp/udp).
- `logging-otel-receiver_forward` — Fluent Forward protocol.
- `logging-otel-receiver_files_refresh_interval` — plain file tailing options.
