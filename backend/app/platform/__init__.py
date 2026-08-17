"""Cross-cutting platform abstractions (config, logging, db, valkey, health).

Domain packages (identity/, conversations/, etc.) may depend on `app.platform`,
never the other way around. No domain code should import a third-party client
(SQLAlchemy engine, valkey client, ...) directly — go through these
abstractions instead.
"""
