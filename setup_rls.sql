-- 开启 RLS (Row Level Security)
ALTER TABLE "影刀社区帖子" ENABLE ROW LEVEL SECURITY;

-- 允许匿名用户 (anon) 读取数据 (SELECT)
-- 这对于前端展示是必须的
CREATE POLICY "Enable read access for all users"
ON "影刀社区帖子"
FOR SELECT
TO anon
USING (true);

-- 允许匿名用户 (anon) 插入数据 (INSERT)
-- 这对于 Python 脚本上传数据是必须的 (如果脚本使用 anon key)
CREATE POLICY "Enable insert access for all users"
ON "影刀社区帖子"
FOR INSERT
TO anon
WITH CHECK (true);

-- 允许匿名用户更新数据 (UPDATE)
-- 可选，方便测试
CREATE POLICY "Enable update access for all users"
ON "影刀社区帖子"
FOR UPDATE
TO anon
USING (true);
