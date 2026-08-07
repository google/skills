# Data Cloud Plugins (Data Agent Kit)

This directory vendors the [Google Data Cloud](https://cloud.google.com/data-cloud) plugins as **git
submodules**, so they can be discovered and installed through the central `google/skills` repository. Each
submodule pins to a specific release tag of its upstream plugin repository, which remains the **source of
truth** for that plugin's skills and MCP server definition.

These plugins package product-specific **Skills** and (where applicable) **MCP servers** for their product's
common user journeys. The set mirrors the layout used by
[`GoogleCloudPlatform/data-agent-kit`](https://github.com/GoogleCloudPlatform/data-agent-kit).

## Installation

### Antigravity CLI (`agy`)

Antigravity CLI installs plugins directly from a repository path. Point `agy` at the plugin you want:

```bash
agy plugin install https://github.com/google/skills/plugins/cloud/data-agent-kit/alloydb
agy plugin install https://github.com/google/skills/plugins/cloud/data-agent-kit/spanner
```

> [!NOTE]
> Submodules are used here because Antigravity CLI does not yet support a marketplace manifest (as Claude Code
> and Codex do). Once marketplace support lands for `agy`, these submodules can be retired in favor of the
> shared manifest.

For Claude Code and Codex, install via the marketplace manifest at the root of this repository instead.

## Included Plugins

Each plugin is pinned to the release tag shown. To update the working tree to the pinned versions, run
`git submodule update --init` from the repo root.

| Product | Repository | Version | Description |
| :--- | :--- | :--- | :--- |
| **AlloyDB for PostgreSQL** | [alloydb](https://github.com/gemini-cli-extensions/alloydb) | `0.2.0` | Create, connect, and interact with an AlloyDB for PostgreSQL database and data. |
| **AlloyDB Omni** | [alloydb-omni](https://github.com/gemini-cli-extensions/alloydb-omni) | `0.2.1` | Create, connect, and interact with an AlloyDB Omni database and data. |
| **BigQuery Data Analytics** | [bigquery-data-analytics](https://github.com/gemini-cli-extensions/bigquery-data-analytics) | `0.2.1` | Connect, query, and generate data insights for BigQuery datasets and data. |
| **Cloud SQL for MySQL** | [cloud-sql-mysql](https://github.com/gemini-cli-extensions/cloud-sql-mysql) | `0.2.0` | Connect and interact with a Cloud SQL for MySQL database and data. |
| **Cloud SQL for PostgreSQL** | [cloud-sql-postgresql](https://github.com/gemini-cli-extensions/cloud-sql-postgresql) | `0.4.0` | Create, connect, and interact with a Cloud SQL for PostgreSQL database and data. |
| **Cloud SQL for SQL Server** | [cloud-sql-sqlserver](https://github.com/gemini-cli-extensions/cloud-sql-sqlserver) | `0.2.0` | Connect to and interact with a Cloud SQL for SQL Server database. |
| **Data Agent Kit Starter Pack** | [data-agent-kit-starter-pack](https://github.com/gemini-cli-extensions/data-agent-kit-starter-pack) | `0.6.1` | A specialized suite of skills for data engineers and database practitioners on Google Cloud — architect data pipelines, transform data with dbt, write Spark/BigQuery notebooks, and orchestrate end-to-end workflows. |
| **Dataproc** | [dataproc](https://github.com/gemini-cli-extensions/dataproc) | `0.1.0` | Manage Dataproc clusters and jobs. |
| **DB Context Engineering Agent** | [db-context-enrichment](https://github.com/GoogleCloudPlatform/db-context-enrichment) | `v0.6.0` | Author and maintain QueryData / Conversational Analytics API context sets that teach the NL→SQL planner your schema vocabulary and golden query shapes. |
| **Firestore** | [firestore-native](https://github.com/gemini-cli-extensions/firestore-native) | `0.3.1` | Connect and interact with Cloud Firestore. |
| **Google Cloud Storage** | [google-cloud-storage](https://github.com/gemini-cli-extensions/google-cloud-storage) | `1.2.0` | Vetted Google Cloud Storage skills for your coding agent. |
| **Knowledge Catalog** | [knowledge-catalog](https://github.com/gemini-cli-extensions/knowledge-catalog) | `0.5.2` | Connect to Knowledge Catalog (formerly Dataplex) to discover, manage, monitor, and govern data and AI artifacts across your data platform. |
| **Looker** | [looker](https://github.com/gemini-cli-extensions/looker) | `0.3.5` | Connect to Looker and interact with your data using LookML. |
| **Oracle Database** | [oracledb](https://github.com/gemini-cli-extensions/oracledb) | `0.2.3` | Connect, query, and interact with Oracle Databases and their data. |
| **Spanner** | [spanner](https://github.com/gemini-cli-extensions/spanner) | `0.3.1` | Connect and interact with Spanner data using natural language. |

## Updating a pinned version

Each submodule's tracked tag is recorded in the top-level `.gitmodules` (`branch = <version>`). To advance a
plugin to a newer release, update its submodule to the new tag and commit the pointer change:

```bash
cd plugins/cloud/data-agent-kit/<plugin>
git fetch --tags
git checkout <new-version>
cd -
git config -f .gitmodules submodule.<plugin>.branch <new-version>
git add .gitmodules plugins/cloud/data-agent-kit/<plugin>
git commit -m "feat(<plugin>): bump to <new-version>"
```
