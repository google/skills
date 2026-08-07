# BigQuery Continuous Queries

BigQuery continuous queries are SQL statements that run continuously in an
unbounded fashion. They let you analyze incoming data in BigQuery in real time.

You can output the results of a continuous query in several ways:

-   Write to a BigQuery table by using an `INSERT` statement.
-   Export to Pub/Sub, Bigtable, or Spanner by using an `EXPORT DATA`
    statement.

## Use Cases

Continuous queries turn BigQuery into an event-driven data processing engine,
unlocking real-time capabilities:

-   Event-Driven Workflows & Agentic Systems: You can trigger downstream
    applications or autonomous agents based on complex events detected in
    incoming data streams. For example, integrate with Pub/Sub to send real-time
    events to downstream agentic systems for further processing.
-   Real-Time AI Inference: Apply generative AI models directly on live data
    streams to generate text or embeddings on the fly, enabling personalized
    customer interactions or real-time anomaly detection.
-   Reverse ETL: Seamlessly push enhanced event data from BigQuery directly
    to operational databases like Spanner or Bigtable for low-latency
    application serving.

## Syntax and Usage

To run a continuous query, you must specify the earliest data to process using
the `APPENDS` function (or `CHANGES` for certain Pub/Sub exports) in the `FROM`
clause.

The start timestamp defines the point in time at which the continuous query
begins processing data.

### Example: Writing to a BigQuery Table

```sql
INSERT INTO `myproject.real_time_taxi_streaming.transformed_taxirides`
SELECT
  timestamp,
  meter_reading,
  ride_status
FROM
  APPENDS(TABLE `myproject.real_time_taxi_streaming.taxirides`,
    CURRENT_TIMESTAMP() - INTERVAL 10 MINUTE)
WHERE
  ride_status = 'dropoff';
```

### Example: Writing to a Pub/Sub Topic

```sql
EXPORT DATA
  OPTIONS (
    format = 'CLOUD_PUBSUB',
    uri = 'https://pubsub.googleapis.com/projects/myproject/topics/taxi-real-time-rides')
AS (
  SELECT
    TO_JSON_STRING(
      STRUCT(
        ride_id,
        timestamp,
        latitude,
        longitude)) AS message,
    TO_JSON(
      STRUCT(
        CAST(passenger_comment AS STRING) AS passenger_comment))
  FROM
    CHANGES(TABLE `myproject.real_time_taxi_streaming.taxi_rides`,
      CURRENT_TIMESTAMP() - INTERVAL 10 MINUTE)
  WHERE _CHANGE_TYPE = 'DELETE'
);
```

## Important Considerations & Limitations

-   Authorization: A continuous query run by a user account runs for a
    maximum of two days and then automatically stops. To run a continuous query
    for up to 150 days, you must use a service account.
-   Reservations: Running continuous queries requires an Enterprise edition
    or Enterprise Plus edition reservation with a `CONTINUOUS` job type
    assignment.
-   Supported Operations: Continuous queries support a limited set of
    stateful operations, such as specific types of `JOIN`s, aggregations, and
    windowing functions. Many standard SQL capabilities like `SELECT DISTINCT`,
    `PIVOT`, and subqueries like `EXISTS` are not supported unless part of a
    supported stateful operation.

For more detail on how to use or structure continuous queries, please refer
to the public documentation for BigQuery continuous queries:
-   https://docs.cloud.google.com/bigquery/docs/continuous-queries-introduction.md.txt
-   https://docs.cloud.google.com/bigquery/docs/continuous-queries.md.txt
-   https://docs.cloud.google.com/bigquery/docs/continuous-query-joins.md.txt
-   https://docs.cloud.google.com/bigquery/docs/window-aggregations.md.txt
-   https://docs.cloud.google.com/bigquery/docs/continuous-queries-monitor.md.txt