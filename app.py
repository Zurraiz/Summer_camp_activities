import os
import json
import sqlite3
import time
import random
import string
import pymysql
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, Response, stream_with_context
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Database Connection Helper (with fallback)
def get_db_connection():
    try:
        # Attempt MySQL connection
        conn = pymysql.connect(
            host=app.config['MYSQL_HOST'],
            port=app.config['MYSQL_PORT'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB'],
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=2
        )
        return conn, "mysql"
    except Exception as e:
        # Fall back to SQLite
        conn = sqlite3.connect(app.config['SQLITE_DB_PATH'])
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

# Unified Query Helper that handles both SQL flavors
def query_db(query, args=(), one=False):
    conn, db_type = get_db_connection()
    if db_type == "sqlite":
        # SQLite uses '?' placeholder instead of '%s'
        query = query.replace('%s', '?')
    
    cursor = conn.cursor()
    try:
        cursor.execute(query, args)
        if query.strip().upper().startswith(('SELECT', 'SHOW')):
            rv = cursor.fetchall()
            if db_type == "sqlite":
                rv = [dict(row) for row in rv]
            return (rv[0] if rv else None) if one else rv
        else:
            conn.commit()
            if query.strip().upper().startswith('INSERT'):
                return cursor.lastrowid
            return cursor.rowcount
    except Exception as e:
        app.logger.error(f"Database error executing query: {query}\nError: {e}")
        return None
    finally:
        conn.close()

# Database Initialization
def init_db():
    conn, db_type = get_db_connection()
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database', 'schema.sql')
    
    if db_type == "sqlite":
        cursor = conn.cursor()
        # Check if students table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='students'")
        if not cursor.fetchone():
            print("Initializing SQLite database with schema...")
            if os.path.exists(schema_path):
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
                # Strip comments line by line first to prevent statements from being skipped
                clean_lines = []
                for line in schema_sql.split('\n'):
                    if not line.strip().startswith('--'):
                        clean_lines.append(line)
                clean_schema_sql = '\n'.join(clean_lines)
                
                statements = clean_schema_sql.split(';')
                for statement in statements:
                    stmt = statement.strip()
                    if not stmt:
                        continue
                    if 'CREATE DATABASE' in stmt or 'USE ' in stmt:
                        continue
                    stmt = stmt.replace('AUTO_INCREMENT', 'AUTOINCREMENT')
                    stmt = stmt.replace('ON DUPLICATE KEY UPDATE id=id', '')
                    # SQLite doesn't support timestamp CURRENT_TIMESTAMP defaults in same way sometimes, but standard sql matches
                    try:
                        cursor.execute(stmt)
                    except Exception as e:
                        print(f"Error executing SQLite schema statement: {e}")
                
                # Manually insert default instructor for SQLite since ON DUPLICATE doesn't exist
                # password hash matches password123
                cursor.execute(
                    "INSERT OR IGNORE INTO instructors (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
                    (1, 'Camp Master', 'instructor@mediatiz.com', 'scrypt:32768:8:1$pYp4fXfB9B9z$db67ad108f9c1db163c46e0129cf65cc870425a815a51a9172bbcb1495c07386008b8b0e8b8398e4f5169a8426ecfa7e781c81ef45db473be90666016e788bc5')
                )
                conn.commit()
        conn.close()
    else:
        # MySQL Mode Initialization
        try:
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES LIKE 'students'")
            if not cursor.fetchone():
                print("Initializing MySQL database with schema...")
                if os.path.exists(schema_path):
                    with open(schema_path, 'r', encoding='utf-8') as f:
                        schema_sql = f.read()
                    statements = schema_sql.split(';')
                    for stmt in statements:
                        stmt = stmt.strip()
                        if stmt and not stmt.startswith('--'):
                            cursor.execute(stmt)
                    conn.commit()
            conn.close()
        except Exception as e:
            print(f"MySQL initialization connection skipped/failed: {e}")

    # Seed default quiz questions if none exist
    try:
        questions_count = query_db("SELECT COUNT(*) as cnt FROM quiz_questions", one=True)
        if questions_count and questions_count['cnt'] == 0:
            print("Seeding quiz questions...")
            default_questions = [
                # Beginner (HTML & CSS)
                ("What does HTML stand for?", "Hyper Text Markup Language", "High Tech Modern Language", "Hyperlink and Text Markup Language", "Home Tool Markup Language", "A", "Beginner"),
                ("Which CSS property is used to change the text color?", "text-color", "color", "font-color", "background-color", "B", "Beginner"),
                ("Which HTML element is used to define the most important heading?", "<head>", "<h6>", "<heading>", "<h1>", "D", "Beginner"),
                ("How do you make a list that lists items with numbers?", "<ol>", "<ul>", "<list>", "<dl>", "A", "Beginner"),
                ("What is the correct CSS syntax to make all <p> elements bold?", "p {text-size: bold;}", "p {font-weight: bold;}", "p {font-style: bold;}", "p {font: bold;}", "B", "Beginner"),
                
                # Intermediate (JavaScript & Python)
                ("How do you write 'Hello World' in an alert box in JavaScript?", "msgBox('Hello World');", "alert('Hello World');", "msg('Hello World');", "alertBox('Hello World');", "B", "Intermediate"),
                ("Which python method is used to add an item to the end of a list?", "add()", "insert()", "append()", "push()", "C", "Intermediate"),
                ("How do you create a function in Python?", "def myFunction():", "function myFunction()", "create myFunction()", "define myFunction()", "A", "Intermediate"),
                ("In JavaScript, what is the output of 'typeof []'?", "\"array\"", "\"object\"", "\"list\"", "\"undefined\"", "B", "Intermediate"),
                ("Which loop is used to execute a block of code a specific number of times?", "for loop", "while loop", "loop-until", "do-while loop", "A", "Intermediate"),
                
                # Advanced (Databases & APIs)
                ("What does SQL stand for?", "Structured Query Language", "Simple Query Language", "Statement Question Language", "Structured Question Layout", "A", "Advanced"),
                ("Which HTTP method is typically used to update an existing resource?", "GET", "POST", "PUT", "DELETE", "C", "Advanced"),
                ("Which clause in SQL is used to filter records in a group?", "WHERE", "HAVING", "GROUP BY", "ORDER BY", "B", "Advanced"),
                ("What is JSON?", "JavaScript Object Notation", "Java System Online Network", "Joint Source Object Namespace", "JavaScript Online Node", "A", "Advanced"),
                ("What does a 404 HTTP status code represent?", "Unauthorized Access", "Server Error", "Success", "Resource Not Found", "D", "Advanced")
            ]
            for q in default_questions:
                query_db(
                    "INSERT INTO quiz_questions (question_text, option_a, option_b, option_c, option_d, correct_answer, topic) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    q
                )
            print("Successfully seeded 15 quiz questions.")
    except Exception as e:
        print(f"Error seeding quiz questions: {e}")

    try:
        wordcloud_count = query_db("SELECT COUNT(*) as cnt FROM wordcloud_words", one=True)
        if wordcloud_count and wordcloud_count['cnt'] == 0:
            default_wordcloud_words = [
                ("Python", 8),
                ("Creative", 5),
                ("Web", 6),
                ("Coding", 9),
                ("Fun", 7),
                ("Innovation", 4),
                ("Summer", 8),
                ("Design", 5),
                ("Learning", 6)
            ]
            for word, weight in default_wordcloud_words:
                query_db(
                    "INSERT INTO wordcloud_words (word, weight) VALUES (%s, %s)",
                    (word, weight)
                )
    except Exception as e:
        print(f"Error seeding wordcloud words: {e}")

# Helper to find rank
def get_student_rank(student_id):
    students = query_db("SELECT id FROM students ORDER BY total_score DESC")
    if not students:
        return 1
    for index, student in enumerate(students):
        if student['id'] == student_id:
            return index + 1
    return len(students)


def get_leaderboard_rows(level_filter='', period='daily'):
    score_column = 'week_score' if period == 'weekly' else 'today_score'
    if level_filter in ['Beginner', 'Intermediate', 'Advanced']:
        return query_db(
            f"SELECT full_name as name, today_score, week_score, grade as level FROM students WHERE grade = %s ORDER BY {score_column} DESC",
            (level_filter,)
        )
    return query_db(
        f"SELECT full_name as name, today_score, week_score, grade as level FROM students ORDER BY {score_column} DESC"
    )


def update_streak(student_id):
    student = query_db("SELECT streak_days, last_active_date FROM students WHERE id = %s", (student_id,), one=True)
    if not student:
        return None

    today = date.today().isoformat()
    if student.get('last_active_date') != today:
        streak_days = int(student.get('streak_days') or 0) + 1
        query_db(
            "UPDATE students SET streak_days = %s, last_active_date = %s WHERE id = %s",
            (streak_days, today, student_id)
        )
    return query_db("SELECT * FROM students WHERE id = %s", (student_id,), one=True)

# -----------------
# Flask Routes
# -----------------

@app.route('/')
def index():
    # Simple statistics
    student_count = query_db("SELECT COUNT(*) as cnt FROM students", one=True)
    total_points = query_db("SELECT SUM(points) as pts FROM point_events", one=True)
    
    stats = {
        'students': student_count['cnt'] if student_count else 0,
        'points': total_points['pts'] if total_points and total_points['pts'] is not None else 0
    }
    return render_template('index.html', stats=stats)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            return render_template('login.html', error='Please enter username and password.')

        student = query_db(
            "SELECT id, username, full_name, grade FROM students WHERE username = %s AND password = %s",
            (username, password),
            one=True
        )

        if student:
            update_streak(student['id'])
            session['student_id'] = student['id']
            session['student_name'] = student['full_name']
            session['student_grade'] = student['grade']
            session['role'] = 'student'
            session['student_level'] = student['grade']
            flash(f"Welcome to Mediatiz, {student['full_name']}!", 'success')
            return redirect(url_for('student_dashboard'))

        return render_template('login.html', error='Invalid username or password.')

    return render_template('login.html')

@app.route('/student/dashboard')
def student_dashboard():
    if session.get('role') != 'student' or 'student_id' not in session:
        flash('Please login first!', 'error')
        return redirect(url_for('login'))
        
    update_streak(session['student_id'])
    student = query_db(
        "SELECT id, full_name as name, grade as level, total_score, today_score, week_score, streak_days, last_active_date FROM students WHERE id = %s",
        (session['student_id'],),
        one=True
    )
    if not student:
        session.clear()
        return redirect(url_for('login'))
        
    session['student_level'] = student['level']
    session['student_grade'] = student['level']
    rank = get_student_rank(student['id'])
    
    # Load point events
    history = query_db(
        "SELECT * FROM point_events WHERE student_id = %s ORDER BY timestamp DESC LIMIT 5",
        (student['id'],)
    )
    
    return render_template('student_dashboard.html', student=student, rank=rank, history=history)

@app.route('/instructor/login', methods=['GET', 'POST'])
def instructor_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        instructor = query_db("SELECT * FROM instructors WHERE email = %s", (email,), one=True)
        if instructor and check_password_hash(instructor['password_hash'], password):
            session['instructor_id'] = instructor['id']
            session['instructor_name'] = instructor['name']
            session['role'] = 'instructor'
            flash('Logged in successfully!', 'success')
            return redirect(url_for('instructor_dashboard'))
        else:
            flash('Invalid email or password!', 'error')
            
    return render_template('instructor_dashboard.html', login_view=True)

@app.route('/instructor/dashboard')
def instructor_dashboard():
    if session.get('role') != 'instructor':
        return redirect(url_for('instructor_login'))
        
    students = query_db("SELECT id, full_name as name, grade as level, total_score FROM students ORDER BY full_name ASC")
    recent_events = query_db(
        "SELECT pe.*, s.full_name as student_name FROM point_events pe JOIN students s ON pe.student_id = s.id ORDER BY pe.timestamp DESC LIMIT 10"
    )
    
    return render_template('instructor_dashboard.html', students=students, events=recent_events, login_view=False)

@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')

# -----------------
# Activities Routes
# -----------------

@app.route('/activities')
def activities():
    return render_template('activities.html')


@app.route('/lesson/<int:id>')
def lesson(id):
    return render_template('lesson.html', lesson_id=id)


@app.route('/activity/brainbuzz')
def brainbuzz():
    if 'role' not in session:
        flash('Please login or join first!', 'error')
        return redirect(url_for('index'))
    return render_template('activities/brainbuzz.html')

@app.route('/activity/hotseat')
def hotseat():
    if 'role' not in session:
        flash('Please login or join first!', 'error')
        return redirect(url_for('index'))
    return render_template('activities/hotseat.html')

@app.route('/activity/wordcloud')
def wordcloud():
    if 'role' not in session:
        flash('Please login or join first!', 'error')
        return redirect(url_for('index'))
    return render_template('activities/wordcloud.html')

# -----------------
# API Endpoints
# -----------------

@app.route('/api/leaderboard')
def api_leaderboard():
    level_filter = request.args.get('level', '')
    period = request.args.get('period', 'daily')
    students = get_leaderboard_rows(level_filter, period)

    return jsonify(students if students else [])


@app.route('/api/leaderboard/stream')
def api_leaderboard_stream():
    level_filter = request.args.get('level', '')
    period = request.args.get('period', 'daily')

    def generate():
        while True:
            students = get_leaderboard_rows(level_filter, period)
            yield f"data: {json.dumps(students if students else [])}\n\n"
            time.sleep(5)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/students')
def api_students():
    students = query_db("SELECT id, full_name as name, grade as level, total_score FROM students ORDER BY full_name ASC")
    return jsonify(students if students else [])


@app.route('/instructor/students')
def instructor_students():
    if session.get('role') != 'instructor':
        return redirect(url_for('instructor_login'))

    students = query_db("SELECT id, username, full_name, grade, today_score, week_score, total_score, streak_days FROM students ORDER BY full_name ASC")
    return render_template('instructor_students.html', students=students if students else [])


@app.route('/api/students/bulk-create', methods=['POST'])
def api_students_bulk_create():
    if session.get('role') != 'instructor':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    names = data.get('names', [])
    grade = data.get('grade', '').strip()

    if not isinstance(names, list) or not grade:
        return jsonify({'error': 'Missing parameters'}), 400

    created = []
    for index, full_name in enumerate(names, start=1):
        name = str(full_name).strip()
        if not name:
            continue

        first_word = name.split()[0].lower()
        first_word = ''.join(ch for ch in first_word if ch.isalnum())
        username = f"{first_word}_{index:02d}" if first_word else f"student_{index:02d}"
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=6))

        student_id = query_db(
            "INSERT INTO students (username, password, full_name, grade) VALUES (%s, %s, %s, %s)",
            (username, password, name, grade)
        )
        if student_id:
            created.append({
                'full_name': name,
                'username': username,
                'password': password,
                'grade': grade
            })

    return jsonify(created)


@app.route('/api/students/delete/', methods=['POST'])
def api_students_delete():
    if session.get('role') != 'instructor':
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    student_id = data.get('id')
    if not student_id:
        return jsonify({'error': 'Missing student id'}), 400

    query_db("DELETE FROM students WHERE id = %s", (student_id,))
    return jsonify({'success': True})

@app.route('/api/quiz/questions')
def api_quiz_questions():
    questions = query_db(
        "SELECT id, question_text, option_a, option_b, option_c, option_d, correct_answer as correct_option FROM quiz_questions ORDER BY RANDOM() LIMIT 5"
        if get_db_connection()[1] == "sqlite"
        else "SELECT id, question_text, option_a, option_b, option_c, option_d, correct_answer as correct_option FROM quiz_questions ORDER BY RAND() LIMIT 5"
    )
        
    return jsonify(questions if questions else [])

@app.route('/api/quiz/submit', methods=['POST'])
def api_quiz_submit():
    if session.get('role') != 'student' or 'student_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.get_json()
    score = data.get('score', 0)
    
    # Award points: score * 10 points
    points_awarded = int(score) * 10
    
    # Update student points
    query_db(
        "UPDATE students SET total_score = total_score + %s, today_score = today_score + %s, week_score = week_score + %s WHERE id = %s",
        (points_awarded, points_awarded, points_awarded, session['student_id'])
    )
    
    # Record point event
    query_db(
        "INSERT INTO point_events (student_id, points, event_type, description) VALUES (%s, %s, %s, %s)",
        (session['student_id'], points_awarded, 'Quiz', f'Completed Quiz (Score: {score}/5)')
    )
    
    return jsonify({'success': True, 'points_awarded': points_awarded})

@app.route('/api/award-points', methods=['POST'])
def api_award_points():
    if session.get('role') != 'instructor':
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.get_json()
    student_id = data.get('student_id')
    points = int(data.get('points', 0))
    description = data.get('description', 'Bonus Points')
    event_type = data.get('event_type', 'Instructor Award')
    
    if not student_id or points == 0:
        return jsonify({'error': 'Missing parameters'}), 400
        
    # Update student points
    query_db(
        "UPDATE students SET total_score = total_score + %s, today_score = today_score + %s, week_score = week_score + %s WHERE id = %s",
        (points, points, points, student_id)
    )

    # Record point event
    query_db(
        "INSERT INTO point_events (student_id, points, event_type, description) VALUES (%s, %s, %s, %s)",
        (student_id, points, event_type, description)
    )

    return jsonify({'success': True})

@app.route('/api/reset-today-scores', methods=['POST'])
def api_reset_today_scores():
    if session.get('role') != 'instructor':
        return jsonify({'error': 'Unauthorized'}), 401

    query_db("UPDATE students SET today_score = 0")
    return jsonify({'success': True})


@app.route('/api/reset-week-scores', methods=['POST'])
def api_reset_week_scores():
    if session.get('role') != 'instructor':
        return jsonify({'error': 'Unauthorized'}), 401

    query_db("UPDATE students SET week_score = 0")
    return jsonify({'success': True})

@app.route('/api/wordcloud/words', methods=['GET', 'POST'])
def api_wordcloud_words():
    if request.method == 'POST':
        data = request.get_json()
        word = data.get('word', '').strip()
        if word:
            conn, db_type = get_db_connection()
            try:
                cursor = conn.cursor()
                if db_type == 'sqlite':
                    cursor.execute("INSERT OR IGNORE INTO wordcloud_words (word) VALUES (?)", (word,))
                    cursor.execute("UPDATE wordcloud_words SET weight = weight + 1 WHERE word = ?", (word,))
                else:
                    cursor.execute(
                        "INSERT INTO wordcloud_words (word, weight) VALUES (%s, 1) ON DUPLICATE KEY UPDATE weight = weight + 1",
                        (word,)
                    )
                conn.commit()
            except Exception as e:
                app.logger.error(f"Database error executing wordcloud update: {e}")
                return jsonify({'error': 'Failed to save word'}), 500
            finally:
                conn.close()

            words = query_db("SELECT word, weight FROM wordcloud_words ORDER BY weight DESC, word ASC")
            
            # Award small participation points (5 pts) for student
            if session.get('role') == 'student' and 'student_id' in session:
                student_id = session['student_id']
                query_db(
                    "UPDATE students SET total_score = total_score + 5, today_score = today_score + 5, week_score = week_score + 5 WHERE id = %s",
                    (student_id,)
                )
                query_db(
                    "INSERT INTO point_events (student_id, points, event_type, description) VALUES (%s, 5, %s, %s)",
                    (student_id, 'WordCloud', f"Submitted word: {word}")
                )
            return jsonify({'success': True, 'words': [{'text': row['word'], 'weight': row['weight']} for row in words] if words else []})

    words = query_db("SELECT word, weight FROM wordcloud_words ORDER BY weight DESC, word ASC")
    return jsonify([{'text': row['word'], 'weight': row['weight']} for row in words] if words else [])


@app.route('/api/buzz/create', methods=['POST'])
def api_buzz_create():
    if session.get('role') != 'instructor' or 'instructor_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    level = data.get('level', '').strip()
    if not level:
        return jsonify({'error': 'Missing level'}), 400

    session_id = query_db(
        "INSERT INTO buzz_sessions (instructor_id, level, status) VALUES (%s, %s, 'waiting')",
        (session['instructor_id'], level)
    )
    return jsonify({'success': True, 'id': session_id})


@app.route('/api/buzz/session/<int:session_id>', methods=['GET'])
def api_buzz_session(session_id):
    buzz_session = query_db("SELECT * FROM buzz_sessions WHERE id = %s", (session_id,), one=True)

    if not buzz_session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify(buzz_session)


@app.route('/api/buzz/respond', methods=['POST'])
def api_buzz_respond():
    if session.get('role') != 'student' or 'student_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    session_id = data.get('session_id')
    question_index = data.get('question_index')
    answer = data.get('answer', '')
    is_correct = 1 if data.get('is_correct') else 0
    points_earned = int(data.get('points_earned', 0))

    if session_id is None or question_index is None:
        return jsonify({'error': 'Missing parameters'}), 400

    query_db(
        "INSERT INTO buzz_responses (session_id, student_id, question_index, answer, is_correct, points_earned) VALUES (%s, %s, %s, %s, %s, %s)",
        (session_id, session['student_id'], question_index, answer, is_correct, points_earned)
    )

    query_db(
        "UPDATE students SET total_score = total_score + %s, today_score = today_score + %s, week_score = week_score + %s WHERE id = %s",
        (points_earned, points_earned, points_earned, session['student_id'])
    )

    if points_earned > 0:
        query_db(
            "INSERT INTO point_events (student_id, points, event_type, description) VALUES (%s, %s, %s, %s)",
            (session['student_id'], points_earned, 'BrainBuzz', 'Brain Buzz answer')
        )

    return jsonify({'success': True})


@app.route('/api/buzz/end/<int:session_id>', methods=['POST'])
def api_buzz_end(session_id):
    if session.get('role') != 'instructor' or 'instructor_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    query_db(
        "UPDATE buzz_sessions SET status = 'ended', ended_at = CURRENT_TIMESTAMP WHERE id = %s",
        (session_id,)
    )
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('index'))

# -----------------
# App Startup
# -----------------

if __name__ == '__main__':
    # Initialize database tables
    init_db()
    
    # Create uploads directory if not exists
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads'), exist_ok=True)
    
    # Run server
    app.run(debug=True, host='0.0.0.0', port=5000)
