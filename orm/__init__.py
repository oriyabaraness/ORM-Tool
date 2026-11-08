"""Cross-jurisdiction regulatory risk comparison (Israel, Jordan, Turkey).

Modules:
    taxonomy  -- risk categories, keyword rules, baseline expectations
    db        -- SQLite schema and query helpers
    sources   -- one connector per regulator, all emitting the same Document shape
    extract   -- PDF text fetching/caching and provision splitting
    classify  -- category tagging and obligation-attribute extraction
    review    -- ORM coordinator notes on a compared pair of clauses
    pipeline  -- orchestration (ingest -> extract -> classify)
"""
