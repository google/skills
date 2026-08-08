# Translating Ops Agent parsing into stock GBOC

The Ops Agent generates OTel configs that rely on **custom OTTL functions**
(`ExtractPatternsRubyRegex`, `IsMatchRubyRegex`) which are **not** compiled into
GBOC. Read the goldens to understand the *target output*, but rebuild it with
stock components: the `filelog` receiver (`regex_parser` operator) plus a
`transform` processor, exporting via `googlecloud`.

## How the `googlecloud` exporter maps a log record

Confirmed from `exporter/collector/logs.go` in `opentelemetry-operations-go`:

| Log record part | Becomes | Notes |
| --- | --- | --- |
| Body (a **map**) | `jsonPayload` | If body is a string → `textPayload`. |
| Attributes | `labels` | Except the special `gcp.*` keys below. |
| `attributes["gcp.http_request"]` (map) | `LogEntry.httpRequest` | Consumed & removed from labels. |
| `attributes["gcp.log_name"]` | `logName` | |
| `attributes["gcp.source_location"]` | `sourceLocation` | |
| `attributes["gcp.trace_sampled"]` | `traceSampled` | |
| `severity_number` / `severity_text` | `severity` | |

So: put user-facing fields in the **body map** (→ `jsonPayload`), and build the
`gcp.http_request` map for the HTTP structure.

## Translation rules

1.  **Regex flavor**: convert Ruby `(?<name>...)` to RE2 `(?P<name>...)`. RE2
    supports non-greedy `*?`/`+?`. Keep the character classes as-is.

2.  **Timestamp**: use the app's `TimeFormat` (strptime directives) directly in
    the `regex_parser` `timestamp` block (`layout:`) — e.g. nginx/apache use
    `%d/%b/%Y:%H:%M:%S %z`.

3.  **`httpRequest`** (access logs): build `attributes["gcp.http_request"]` with
    the LogEntry HttpRequest field names: `remoteIp`, `requestMethod`,
    `requestUrl`, `protocol`, `status`, `responseSize`, `referer`, `userAgent`.
    -   Cast `status` to an integer (`Int(...)`).
    -   Leave `responseSize` a **string** (matches Ops Agent; the exporter
        accepts it).

4.  **Type casts**: mirror the app's `ParserShared.Types` map. Fields marked
    `integer` there get `Int(...)`; everything else stays a string.

5.  **Severity**: if `apps/<app>.go` has a `LoggingProcessorModifyFields` block
    mapping a parsed level to `severity` (e.g. `error` → `ERROR`), reproduce it
    by setting `severity_text` (and `severity_number` to 0 so the exporter
    re-derives the number from the text). Access-log parsers usually set **no**
    severity — don't invent one.

6.  **Omit `-` placeholders**: apache/nginx-style parsers drop fields whose value
    is `-` (e.g. `referer`, `host`, `user`). Use
    `delete_key(..., "x") where IsMatch(x, "^-$")`.

7.  **Log name**: set the exporter `default_log_name` (or
    `attributes["gcp.log_name"]`) to the receiver type, e.g. `nginx_access`.

## Worked example: `nginx_access`

Ops Agent regex (`apps/common_logging_processors.go`, `genericAccessLogParser`),
converted to RE2, plus the transform that produces Ops-Agent-equivalent output.

```yaml
receivers:
  filelog/nginx:
    include:
      - /var/log/nginx/access.log   # replace with the actual path
    start_at: end                   # use "beginning" only for testing
    operators:
      - type: regex_parser
        parse_from: body
        parse_to: body
        regex: '^(?P<http_request_remoteIp>[^ ]*) (?P<host>[^ ]*) (?P<user>[^ ]*) \[(?P<time>[^\]]*)\] "(?P<http_request_requestMethod>\S+)(?: +(?P<http_request_requestUrl>[^"]*?)(?: +(?P<http_request_protocol>\S+))?)?" (?P<http_request_status>[^ ]*) (?P<http_request_responseSize>[^ ]*)(?: "(?P<http_request_referer>[^"]*)" "(?P<http_request_userAgent>[^"]*)")?(?: "(?P<gzip_ratio>[^"]*)")?$'
        timestamp:
          parse_from: body.time
          layout: '%d/%b/%Y:%H:%M:%S %z'

processors:
  transform/nginx_access:
    error_mode: ignore
    log_statements:
      - context: log
        statements:
          - set(body["http_request_status"], Int(body["http_request_status"])) where body["http_request_status"] != nil
          - set(attributes["gcp.http_request"]["remoteIp"], body["http_request_remoteIp"]) where body["http_request_remoteIp"] != nil
          - set(attributes["gcp.http_request"]["requestMethod"], body["http_request_requestMethod"]) where body["http_request_requestMethod"] != nil
          - set(attributes["gcp.http_request"]["requestUrl"], body["http_request_requestUrl"]) where body["http_request_requestUrl"] != nil
          - set(attributes["gcp.http_request"]["protocol"], body["http_request_protocol"]) where body["http_request_protocol"] != nil
          - set(attributes["gcp.http_request"]["status"], body["http_request_status"]) where body["http_request_status"] != nil
          - set(attributes["gcp.http_request"]["responseSize"], body["http_request_responseSize"]) where body["http_request_responseSize"] != nil
          - set(attributes["gcp.http_request"]["userAgent"], body["http_request_userAgent"]) where body["http_request_userAgent"] != nil
          - set(attributes["gcp.http_request"]["referer"], body["http_request_referer"]) where body["http_request_referer"] != nil
          - delete_key(attributes["gcp.http_request"], "referer") where (attributes["gcp.http_request"] != nil and attributes["gcp.http_request"]["referer"] != nil and IsMatch(body["http_request_referer"], "^-$"))
          - delete_key(body, "http_request_remoteIp")
          - delete_key(body, "http_request_requestMethod")
          - delete_key(body, "http_request_requestUrl")
          - delete_key(body, "http_request_protocol")
          - delete_key(body, "http_request_status")
          - delete_key(body, "http_request_responseSize")
          - delete_key(body, "http_request_referer")
          - delete_key(body, "http_request_userAgent")
          - delete_key(body, "time")
          - delete_key(body, "host") where (body["host"] == nil or IsMatch(body["host"], "^-$"))
          - delete_key(body, "user") where (body["user"] == nil or IsMatch(body["user"], "^-$"))
          - delete_key(body, "gzip_ratio") where (body["gzip_ratio"] == nil or body["gzip_ratio"] == "" or IsMatch(body["gzip_ratio"], "^-$"))

exporters:
  googlecloud:
    log:
      default_log_name: nginx_access

service:
  pipelines:
    logs/nginx:
      receivers: [filelog/nginx]
      processors: [memory_limiter, transform/nginx_access, resourcedetection, batch]
      exporters: [googlecloud]
```

### Adapting to other apps

-   **Other access logs** (apache/jetty/tomcat/couchbase/iis): same
    `genericAccessLogParser` regex and `httpRequest` construction; only the
    include path and `default_log_name` change.
-   **Error/system logs** (nginx_error, mysql_error, etc.): usually a different
    regex and a severity `ModifyFields` mapping instead of `httpRequest`. Copy
    the regex from `apps/<app>.go`, keep parsed fields in the body
    (`jsonPayload`), and translate the severity mapping to `severity_text`.
-   **JSON logs** (elasticsearch_json): replace `regex_parser` with a
    `json_parser` operator (`parse_to: body`); map the timestamp and severity
    fields the app specifies.
