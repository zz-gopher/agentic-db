-- ==========================================
-- 1. 彻底清理环境 (顺序删除，防止外键等潜在冲突)
-- ==========================================
DROP TABLE IF EXISTS note_tags;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS comments;
DROP TABLE IF EXISTS users;
-- 这两个保持不变
DROP TABLE IF EXISTS notes;
DROP TABLE IF EXISTS notebooks;

-- ==========================================
-- 2. 重建所有表结构 (保持原汁原味)
-- ==========================================
CREATE TABLE notebooks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME(6) NOT NULL,
    description VARCHAR(500) NULL,
    title VARCHAR(100) NOT NULL,
    updated_at DATETIME(6) NOT NULL
);

CREATE TABLE notes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    content TEXT NULL,
    created_at DATETIME(6) NOT NULL,
    notebook_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    user_id BIGINT NULL
);

CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(50),
    status VARCHAR(2),
    create_time DATETIME(6)
);

CREATE TABLE comments (
    id BIGINT PRIMARY KEY,
    note_id BIGINT,
    user_id BIGINT,
    content TEXT,
    create_time DATETIME(6)
);

CREATE TABLE tags (
    id BIGINT PRIMARY KEY,
    tag_name VARCHAR(50)
);

CREATE TABLE note_tags (
    note_id BIGINT,
    tag_id BIGINT,
    PRIMARY KEY(note_id, tag_id)
);

-- ==========================================
-- 3. 灌入全量测试数据 (覆盖各类边界)
-- ==========================================
INSERT INTO notebooks (id, created_at, description, title, updated_at) VALUES
(1024, '2023-01-01 10:00:00.000000', '工作相关', '工作笔记', '2023-01-01 10:00:00.000000'),
(1025, '2024-01-01 10:00:00.000000', '个人学习', '学习笔记', '2024-01-01 10:00:00.000000');

INSERT INTO users (id, username, status, create_time) VALUES
(1, '架构师老李', '1', '2023-05-10 10:00:00.000000'),
(2, '开发小王', '0', '2023-06-15 14:00:00.000000'),
(3, '测试小美', '1', '2024-01-01 09:00:00.000000');

INSERT INTO notes (id, content, created_at, notebook_id, title, updated_at, user_id) VALUES
(1, '深入理解生成器...', '2023-10-01 10:00:00.000000', 1024, 'Python高级学习指南', '2023-10-01 10:00:00.000000', 1),
(2, '今天遇到一个慢查询...', '2023-10-02 10:00:00.000000', 1024, 'MySQL调优日记', '2023-10-02 10:00:00.000000', 1),
(3, '安装CUDA环境...', '2024-02-15 09:00:00.000000', 1025, '深度学习环境配置', '2024-02-15 09:00:00.000000', 2);

INSERT INTO comments (id, note_id, user_id, content, create_time) VALUES
(1, 1, 1, '这篇文章对我帮助很大！', '2023-10-01 11:00:00.000000'),
(2, 1, 2, '标记一下，周末看。', '2023-10-02 15:00:00.000000'),
(3, 2, 1, '这个坑我也踩过！', '2024-01-05 08:00:00.000000');

INSERT INTO tags (id, tag_name) VALUES
(1, '后端开发'),
(2, '性能优化'),
(3, '日常吐槽');

INSERT INTO note_tags (note_id, tag_id) VALUES
(1, 1),
(1, 2),
(2, 2),
(2, 3),
(3, 1);