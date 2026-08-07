# CLI Usage

Common `gcloud` commands for interacting with Spanner. For instructions on how
to install the Google Cloud SDK, see
[Install the Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).

## Instances

### List Instances

```bash
gcloud spanner instances list
```

### Create Instance

```bash
# Fixed nodes
gcloud spanner instances create my-instance \
    --config=regional-us-central1 \
    --description="My Instance" \
    --nodes=1

# Autoscaler
gcloud spanner instances create my-autoscaled-instance \
    --config=regional-us-central1 \
    --description="My Autoscaled Instance" \
    --autoscaling-min-nodes=1 \
    --autoscaling-max-nodes=3
```

## Databases

### List Databases

```bash
gcloud spanner databases list --instance=my-instance
```

### Create Database

```bash
gcloud spanner databases create my-database --instance=my-instance
```

## Execute Query

```bash
gcloud spanner databases execute-sql my-database --instance=my-instance --sql="SELECT 1"
```

## Backups

### Create Backup

```bash
gcloud spanner backups create my-backup \
    --instance=my-instance \
    --database=my-database \
    --retention-period=7d
```

## Operations

### List Operations

```bash
gcloud spanner operations list --instance=my-instance
```
