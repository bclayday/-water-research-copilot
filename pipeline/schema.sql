CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learning_goals (
    goal_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    publication_year INTEGER,
    doi TEXT,
    cited_by_count INTEGER DEFAULT 0,
    is_open_access BOOLEAN DEFAULT FALSE,
    concepts TEXT[] DEFAULT '{}',
    raw_json JSONB DEFAULT '{}'::jsonb,
    ingested_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS authors (
    author_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    orcid TEXT,
    institution TEXT,
    raw_json JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    author_id TEXT NOT NULL REFERENCES authors(author_id) ON DELETE CASCADE,
    author_position INTEGER,
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS collections (
    collection_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS collection_papers (
    collection_id INTEGER NOT NULL REFERENCES collections(collection_id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    saved_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (collection_id, paper_id)
);

CREATE TABLE IF NOT EXISTS reading_progress (
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'not_started',
    notes TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, paper_id),
    CONSTRAINT reading_progress_status_chk CHECK (status IN ('not_started', 'reading', 'completed'))
);

CREATE TABLE IF NOT EXISTS paper_embeddings (
    embedding_id SERIAL PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (paper_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS water_stations (
    site_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    latitude FLOAT,
    longitude FLOAT,
    watershed TEXT,
    county TEXT
);

CREATE TABLE IF NOT EXISTS raw_readings (
    raw_id BIGSERIAL PRIMARY KEY,
    source_system TEXT NOT NULL DEFAULT 'usgs_nwis',
    payload JSONB NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS water_readings (
    reading_id SERIAL PRIMARY KEY,
    site_id TEXT REFERENCES water_stations(site_id) ON DELETE CASCADE,
    parameter_code TEXT NOT NULL,
    parameter_name TEXT NOT NULL,
    value FLOAT,
    unit TEXT,
    reading_time TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT water_readings_site_param_time_uniq UNIQUE (site_id, parameter_code, reading_time)
);

CREATE TABLE IF NOT EXISTS water_anomalies (
    anomaly_id SERIAL PRIMARY KEY,
    site_id TEXT REFERENCES water_stations(site_id) ON DELETE CASCADE,
    parameter_name TEXT NOT NULL,
    value FLOAT,
    threshold FLOAT,
    severity TEXT,
    detected_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(publication_year);
CREATE INDEX IF NOT EXISTS idx_papers_citations ON papers(cited_by_count DESC);
CREATE INDEX IF NOT EXISTS idx_water_readings_site_time ON water_readings(site_id, reading_time DESC);
CREATE INDEX IF NOT EXISTS idx_water_anomalies_site_time ON water_anomalies(site_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_embeddings_vector ON paper_embeddings USING hnsw (embedding vector_cosine_ops);
