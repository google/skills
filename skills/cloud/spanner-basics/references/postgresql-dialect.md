# PostgreSQL Dialect Support

Spanner provides PostgreSQL dialect support by expressing Spanner database
features through a subset of open source PostgreSQL dialect constructs.

## Key Considerations

*   **Portability**: Easier migration to other PostgreSQL databases if needed.
*   **Familiarity**: Leverages existing knowledge of PostgreSQL syntax and
    tools.
*   **Ecosystem**: Supports tools like `psql` and PostgreSQL drivers (via
    PGAdapter).

## Features and Extensions

Spanner includes extensions to support Spanner-specific features within the
PostgreSQL dialect:

- Interleaved tables
- Time to live (TTL)
- Query hints

## Limitations

Spanner does not support some open source PostgreSQL features: 

- Triggers 
- `SERIAL` 
- Transactional DDL 
- User-defined data types and operators

For more information, see
[The PostgreSQL language in Spanner](https://docs.cloud.google.com/spanner/docs/reference/postgresql/overview.md.txt).
