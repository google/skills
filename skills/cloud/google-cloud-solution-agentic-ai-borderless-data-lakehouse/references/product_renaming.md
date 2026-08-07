# Product Renaming & Terminology

When generating solution designs, architecture diagrams, and documentation, use
the updated Google Cloud product names. Note that underlying APIs, Terraform
resources, and IAM roles often retain their legacy identifiers.

<table>
  <thead>
    <tr>
      <th>Legacy Name</th>
      <th>Updated Name</th>
      <th>Notes / API Identifiers</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Vertex AI</td>
      <td>Gemini Enterprise Agent Platform</td>
      <td>Used for AI serving and agentic workflows.</td>
    </tr>
    <tr>
      <td>BigLake</td>
      <td>Lakehouse for Apache Iceberg</td>
      <td>
        Used for central metadata and governance. Terraform resources (e.g.,
        <code>google_biglake_table</code>,
        <code>google_biglake_repository</code>) and APIs still use
        <code>biglake</code>.
      </td>
    </tr>
    <tr>
      <td>Dataproc Serverless</td>
      <td>Managed Service for Apache Spark</td>
      <td>
        Used for distributed processing. APIs and IAM roles still use
        <code>dataproc</code>.
      </td>
    </tr>
    <tr>
      <td>Dataplex</td>
      <td>Knowledge Catalog</td>
      <td>Used for active context and governance.</td>
    </tr>
    <tr>
      <td>cross-cloud, multicloud, multi-cloud</td>
      <td>borderless</td>
      <td>
        Rephrase all occurrences to <code>borderless</code>, with the exception
        of the product <code>Cross-Cloud Interconnect</code>.
      </td>
    </tr>
  </tbody>
</table>
