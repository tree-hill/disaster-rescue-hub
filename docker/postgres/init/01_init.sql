-- 初始化扩展（PostgreSQL 15.5）
-- 在 disaster_rescue 数据库上执行

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- crypt() 密码哈希备用
