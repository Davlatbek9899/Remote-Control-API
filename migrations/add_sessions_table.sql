-- Bitta hisob bilan bir vaqtning o'zida faqat bitta qurilmada kirish mumkin bo'lishi uchun.
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_name TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_active ON sessions (user_id, is_active);

-- Qurilmaning Telegram buyruq paroli — "sessiyani tugatish" bosilganda, serverning
-- o'sha parolning navbatiga to'g'ridan-to'g'ri signal yuborishi uchun kerak.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS command_password TEXT;
