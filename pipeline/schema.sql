CREATE EXTENSION IF NOT EXISTS vector;

-- Users and goals
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learning_goals (
    goal_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Papers
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    publication_year INTEGER,
    doi TEXT,
    cited_by_count INTEGER DEFAULT 0,
    is_open_access BOOLEAN DEFAULT FALSE,
    concepts TEXT[],
    raw_json JSONB,
    ingested_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS authors (
    author_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    institution TEXT,
    orcid TEXT
);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id TEXT REFERENCES papers(paper_id) ON DELETE CASCADE,
    author_id TEXT REFERENCES authors(author_id) ON DELETE CASCADE,
    author_position INTEGER DEFAULT 0,
    PRIMARY KEY (paper_id, author_id)
);

-- Collections and progress
CREATE TABLE IF NOT EXISTS collections (
    collection_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS collection_papers (
    collection_id INTEGER REFERENCES collections(collection_id) ON DELETE CASCADE,
    paper_id TEXT REFERENCES papers(paper_id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (collection_id, paper_id)
);

CREATE TABLE IF NOT EXISTS reading_progress (
    progress_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    paper_id TEXT REFERENCES papers(paper_id) ON DELETE CASCADE,
    status TEXT DEFAULT 'not_started',
    notes TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, paper_id)
);

-- Embeddings
CREATE TABLE IF NOT EXISTS paper_embeddings (
    embedding_id SERIAL PRIMARY KEY,
    paper_id TEXT REFERENCES papers(paper_id) ON DELETE CASCADE,
    chunk_index INTEGER DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    model_name TEXT DEFAULT 'all-MiniLM-L6-v2',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_embeddings_hnsw
ON paper_embeddings USING hnsw (embedding vector_cosine_ops);
