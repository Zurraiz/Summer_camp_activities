-- Students table
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    camp_code TEXT NOT NULL,
    level TEXT NOT NULL,
    total_score INTEGER DEFAULT 0,
    today_score INTEGER DEFAULT 0,
    week_score INTEGER DEFAULT 0,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    streak_days INTEGER DEFAULT 0,
    last_active_date TEXT DEFAULT NULL
);

-- Instructors table
CREATE TABLE IF NOT EXISTS instructors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Point Events table
CREATE TABLE IF NOT EXISTS point_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    points INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

-- Quiz Questions table
CREATE TABLE IF NOT EXISTS quiz_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct_option TEXT NOT NULL,
    difficulty TEXT DEFAULT 'Intermediate'
);

-- Brain Buzz Sessions table
CREATE TABLE IF NOT EXISTS buzz_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instructor_id INTEGER,
    level TEXT,
    status TEXT DEFAULT 'waiting',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

-- Brain Buzz Responses table
CREATE TABLE IF NOT EXISTS buzz_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    student_id INTEGER,
    question_index INTEGER,
    answer TEXT,
    is_correct INTEGER DEFAULT 0,
    points_earned INTEGER DEFAULT 0,
    responded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Wordcloud Words table
CREATE TABLE IF NOT EXISTS wordcloud_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE,
    weight INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);