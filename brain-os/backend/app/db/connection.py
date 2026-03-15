"""PostgreSQL connection pool. When DATABASE_URL is set, use PG; otherwise None."""
from __future__ import annotations

import os
from typing import Any

_pool = None


async def get_pool():
    global _pool
    if _pool is None and os.environ.get("DATABASE_URL"):
        import asyncpg
        _pool = await asyncpg.create_pool(
            os.environ["DATABASE_URL"],
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
    return _pool


async def init_db() -> bool:
    """Create tables if using PostgreSQL. Returns True if DB is in use."""
    pool = await get_pool()
    if pool is None:
        return False
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                external_id TEXT,
                version INT DEFAULT 1,
                status TEXT DEFAULT 'pending',
                last_verified_at TIMESTAMPTZ,
                freshness_score FLOAT,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_audit (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                action TEXT NOT NULL,
                prev_hash TEXT,
                new_hash TEXT,
                chain_prev_id TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS unanswered_questions (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                question TEXT NOT NULL,
                count INT DEFAULT 1,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                CONSTRAINT uq_unanswered UNIQUE (tenant_id, namespace, question)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gap_reports (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                report JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS brain_settings (
                tenant_id TEXT PRIMARY KEY,
                brain_name TEXT NOT NULL DEFAULT 'My Brain',
                domain TEXT NOT NULL DEFAULT 'custom',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_questions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                question TEXT NOT NULL,
                label TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_saved_questions_tenant ON saved_questions(tenant_id);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS suggested_edits (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                question TEXT NOT NULL,
                original_answer TEXT,
                user_edit TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS answer_feedback (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                question TEXT NOT NULL,
                answer_excerpt TEXT,
                helpful BOOLEAN NOT NULL,
                what_wrong TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        # Add user_key for per-user preference inference (idempotent)
        await conn.execute("""
            DO $$ BEGIN
                ALTER TABLE answer_feedback ADD COLUMN user_key TEXT DEFAULT 'default';
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_answers (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                citations_json TEXT,
                tag TEXT,
                note TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_saved_answers_tenant ON saved_answers(tenant_id);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS export_state (
                namespace TEXT PRIMARY KEY,
                exported_hashes JSONB NOT NULL DEFAULT '[]',
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        # Claims (extracted from chunks) — for timeline, freshness per claim, contradiction detection
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                document_name TEXT NOT NULL,
                claim_text TEXT NOT NULL,
                valid_from TIMESTAMPTZ DEFAULT NOW(),
                valid_until TIMESTAMPTZ,
                last_verified_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_claims_namespace ON claims(tenant_id, namespace);
            CREATE INDEX IF NOT EXISTS idx_claims_document ON claims(document_id);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS claim_versions (
                id SERIAL PRIMARY KEY,
                claim_id TEXT NOT NULL,
                claim_text TEXT NOT NULL,
                valid_from TIMESTAMPTZ NOT NULL,
                valid_until TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_claim_versions_claim ON claim_versions(claim_id);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contradictions (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                claim_id_a TEXT NOT NULL,
                claim_id_b TEXT NOT NULL,
                document_name_a TEXT NOT NULL,
                document_name_b TEXT NOT NULL,
                claim_text_a TEXT NOT NULL,
                claim_text_b TEXT NOT NULL,
                summary TEXT,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_contradictions_namespace ON contradictions(tenant_id, namespace);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS source_trust (
                document_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                trust_score FLOAT NOT NULL DEFAULT 0.5,
                citation_count INT DEFAULT 0,
                helpful_count INT DEFAULT 0,
                correction_count INT DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (document_id, tenant_id, namespace)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS answer_proved_wrong (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                question TEXT NOT NULL,
                answer_excerpt TEXT,
                citation_doc_ids TEXT[],
                marked_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_answer_proved_wrong_lookup ON answer_proved_wrong(tenant_id, namespace);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS query_citations (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                question TEXT NOT NULL,
                cited_document_ids JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_query_citations_namespace ON query_citations(tenant_id, namespace);
        """)
        # Persistent cognitive memory
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                interaction_summary TEXT NOT NULL,
                question TEXT,
                answer_excerpt TEXT,
                facts_extracted JSONB DEFAULT '[]',
                importance_score FLOAT DEFAULT 0.5,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_episodic_tenant_namespace ON episodic_memory(tenant_id, namespace);
            CREATE INDEX IF NOT EXISTS idx_episodic_created ON episodic_memory(created_at DESC);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                user_key TEXT NOT NULL,
                key TEXT NOT NULL,
                value JSONB NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, namespace, user_key, key)
            );
            CREATE INDEX IF NOT EXISTS idx_user_memory_lookup ON user_memory(tenant_id, namespace, user_key);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS outcome_memory (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                run_type TEXT NOT NULL,
                run_id TEXT,
                success BOOLEAN NOT NULL,
                retrieval_success BOOLEAN,
                tool_success BOOLEAN,
                user_satisfaction FLOAT,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_outcome_tenant ON outcome_memory(tenant_id, namespace);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_plans (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                goal TEXT NOT NULL,
                tasks JSONB NOT NULL DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                outcome_success BOOLEAN,
                steps_log JSONB DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        # OAuth tool connections (Gmail, Slack, Drive)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS connected_tools (
                tenant_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'connected',
                metadata JSONB DEFAULT '{}',
                connected_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (tenant_id, provider)
            );
        """)
        # Knowledge capture queue (from Slack/email; approve -> ingest)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_capture_queue (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'main',
                source_type TEXT NOT NULL DEFAULT 'slack',
                source_id TEXT,
                question TEXT NOT NULL,
                answer_text TEXT NOT NULL,
                quality_score FLOAT DEFAULT 0.5,
                sensitivity_score FLOAT DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                approved_at TIMESTAMPTZ
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_capture_tenant ON knowledge_capture_queue(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_capture_status ON knowledge_capture_queue(status);
        """)
        # Personal profiles (preferences inferred from feedback; used at query time)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS personal_profiles (
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                user_key TEXT NOT NULL,
                preferences JSONB DEFAULT '{}',
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (tenant_id, namespace, user_key)
            );
            CREATE INDEX IF NOT EXISTS idx_personal_profiles_lookup ON personal_profiles(tenant_id, namespace, user_key);
        """)
        # Compliance audit log (PII scans, URL verdicts)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_audit (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_compliance_audit_tenant ON compliance_audit(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_compliance_audit_kind ON compliance_audit(kind);
            CREATE INDEX IF NOT EXISTS idx_compliance_audit_created ON compliance_audit(created_at DESC);
        """)
        # Document change log (timeline when URL sources are re-fetched)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS document_changes_log (
                id SERIAL PRIMARY KEY,
                document_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                changed_at TIMESTAMPTZ DEFAULT NOW(),
                semantic_summary TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_document_changes_log_doc ON document_changes_log(document_id);
        """)
        # Proactive assistant: one offer per thread, then silence
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS proactive_offer_made (
                team_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                thread_ts TEXT NOT NULL,
                feature TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (team_id, channel_id, thread_ts, feature)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS proactive_opt_out (
                team_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                feature TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (team_id, user_id, feature)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS slack_quiet_channels (
                team_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (team_id, channel_id)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS proactive_flows (
                id TEXT PRIMARY KEY,
                team_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                thread_ts TEXT NOT NULL,
                feature TEXT NOT NULL,
                state TEXT NOT NULL,
                payload JSONB DEFAULT '{}',
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_proactive_flows_thread ON proactive_flows(team_id, channel_id, thread_ts);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS standup_config (
                team_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                hour INT NOT NULL DEFAULT 9,
                minute INT NOT NULL DEFAULT 30,
                timezone TEXT DEFAULT 'UTC',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (team_id, channel_id)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS standup_submissions (
                id SERIAL PRIMARY KEY,
                team_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                submission_date DATE NOT NULL,
                yesterday_text TEXT,
                today_text TEXT,
                blockers_text TEXT,
                submitted_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(team_id, channel_id, user_id, submission_date)
            );
            CREATE INDEX IF NOT EXISTS idx_standup_submissions_date ON standup_submissions(team_id, channel_id, submission_date);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS task_reminders_sent (
                id SERIAL PRIMARY KEY,
                team_id TEXT NOT NULL,
                sheet_id TEXT NOT NULL,
                task_id_or_row TEXT NOT NULL,
                user_id TEXT NOT NULL,
                due_date DATE NOT NULL,
                sent_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(team_id, sheet_id, task_id_or_row, user_id, due_date)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_dm_sent (
                team_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                sent_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (team_id, user_id)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS brainos_project_sheets (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                sheet_id TEXT NOT NULL,
                sheet_url TEXT,
                project_name TEXT NOT NULL,
                tasks_json JSONB DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_brainos_sheets_tenant ON brainos_project_sheets(tenant_id);
        """)
        # Extension: watched pages for competitive intelligence (url, last content, diff)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS extension_watched_pages (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'main',
                user_key TEXT NOT NULL DEFAULT 'default',
                url TEXT NOT NULL,
                last_content TEXT,
                last_content_hash TEXT,
                last_checked_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, namespace, user_key, url)
            );
            CREATE INDEX IF NOT EXISTS idx_extension_watched_tenant ON extension_watched_pages(tenant_id, namespace);
        """)
    return True


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
