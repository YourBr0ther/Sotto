-- Sotto Operational Database Schema
-- SQLite database for active task queue, heartbeat management, and device state

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'reminded', 'snoozed', 'completed', 'overdue')),
    created_at TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    due_at TIMESTAMP,
    next_remind_at TIMESTAMP,
    remind_count INTEGER DEFAULT 0,
    obsidian_path TEXT,
    source TEXT CHECK(source IN ('conversation', 'calendar', 'email', 'manual')),
    context TEXT,
    is_private BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS heartbeat_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_at TIMESTAMP NOT NULL,
    delivered_at TIMESTAMP,
    content_type TEXT CHECK(content_type IN ('task_reminder', 'calendar', 'email', 'alert', 'briefing')),
    content TEXT NOT NULL,
    priority INTEGER DEFAULT 5 CHECK(priority BETWEEN 1 AND 10),
    is_private BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS device_state (
    device_id TEXT PRIMARY KEY,
    device_type TEXT CHECK(device_type IN ('phone', 'pi5', 'io-controller')),
    last_seen TIMESTAMP,
    battery_percent INTEGER,
    audio_quality_avg FLOAT,
    mode TEXT CHECK(mode IN ('active', 'input_only', 'quiet', 'sleep')),
    headphones_connected BOOLEAN
);

CREATE TABLE IF NOT EXISTS processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    audio_quality FLOAT,
    transcription_confidence FLOAT,
    action_taken TEXT CHECK(action_taken IN ('task_created', 'note_updated', 'classified_private', 'discarded', 'error')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS agent_metrics (
    date TEXT PRIMARY KEY,
    tasks_created INTEGER DEFAULT 0,
    tasks_completed INTEGER DEFAULT 0,
    heartbeats_delivered INTEGER DEFAULT 0,
    transcription_failures INTEGER DEFAULT 0,
    avg_audio_quality FLOAT,
    notes TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_next_remind ON tasks(next_remind_at);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_heartbeat_scheduled ON heartbeat_queue(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_heartbeat_delivered ON heartbeat_queue(delivered_at);
CREATE INDEX IF NOT EXISTS idx_processing_log_timestamp ON processing_log(timestamp);
