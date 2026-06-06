-- ============================================================================
-- 進階（選用）：資料量變大時，把語意向量從「JSON text 欄位 + Python 算 cosine」
-- 升級成 pgvector 的最近鄰查詢。目前預設用 text 欄位（見 supabase/schema.sql），
-- 規模還小時不需要這份；要升級時再在 Supabase SQL Editor 執行。
--
-- 維度需與 matching.EMBED_DIM 一致（目前 1024，Jina embeddings v3 預設）。
-- ============================================================================

-- 1) 啟用 pgvector
create extension if not exists vector;

-- 2) 招領物與遺失通報各加一個 vector 欄位
--    （與現有的 text embedding 欄位並存；遷移時把 JSON 轉成 vector 後即可改用）
alter table lost_items   add column if not exists embedding_vec vector(1024);
alter table lost_reports add column if not exists embedding_vec vector(1024);

-- 3) 近似最近鄰索引（cosine）。lists 約可抓 rows / 1000。
create index if not exists lost_items_embedding_idx
  on lost_items   using ivfflat (embedding_vec vector_cosine_ops) with (lists = 100);
create index if not exists lost_reports_embedding_idx
  on lost_reports using ivfflat (embedding_vec vector_cosine_ops) with (lists = 100);

-- 4) 正向媒合：新通報 -> 找最相近的招領物
create or replace function match_lost_items(
  query_embedding vector(1024),
  match_count int default 50
)
returns table (id integer, cosine float)
language sql stable as $$
  select lost_items.id, 1 - (lost_items.embedding_vec <=> query_embedding) as cosine
  from lost_items
  where lost_items.embedding_vec is not null
  order by lost_items.embedding_vec <=> query_embedding
  limit match_count;
$$;

-- 5) 反向媒合：新招領物 -> 找最相近的現有通報
create or replace function match_lost_reports(
  query_embedding vector(1024),
  match_count int default 50
)
returns table (id bigint, cosine float)
language sql stable as $$
  select lost_reports.id, 1 - (lost_reports.embedding_vec <=> query_embedding) as cosine
  from lost_reports
  where lost_reports.embedding_vec is not null
  order by lost_reports.embedding_vec <=> query_embedding
  limit match_count;
$$;

-- ============================================================================
-- 升級步驟（text embedding -> pgvector）
-- ----------------------------------------------------------------------------
-- 1. 執行本檔建立 vector 欄位 / 索引 / RPC。
-- 2. 把既有 text 欄位的 JSON 向量回填到 embedding_vec（一次性轉換）。
-- 3. 在 app.py 的媒合改用上述 RPC（或直接用 <=> 運算子）取代 Python cosine。
-- ============================================================================
