from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, session
import sqlite3
import pandas as pd
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'campusfix_secret_key_change_me'
DB_PATH = 'campus.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    with open('schema.sql', 'r') as f:
        conn.executescript(f.read())
    
    cursor = conn.cursor()
    # Create default admin user if missing
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
    
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('student_login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Route: Student Login (Allows ANY password to be created/used)
@app.route('/login/student', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        scholar_no = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        # Validation for 6-digit scholar number
        if not scholar_no.isdigit() or len(scholar_no) != 6:
            return render_template('student_login.html', error="Please enter a valid 6-digit Scholar Number.")

        if not password:
            return render_template('student_login.html', error="Please enter a password.")

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if student already exists in the database
        user = cursor.execute('SELECT * FROM users WHERE username = ? AND role = "student"', (scholar_no,)).fetchone()
        
        if user:
            # If student exists, check if password matches what they previously set
            if user['password'] == password:
                session['user_id'] = user['id']
                session['username'] = scholar_no
                session['role'] = user['role']
                conn.close()
                return redirect(url_for('dashboard'))
            else:
                conn.close()
                return render_template('student_login.html', error="Incorrect password for this Scholar Number.")
        else:
            # If student does NOT exist, register them instantly with the password they typed
            cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, "student")', (scholar_no, password))
            conn.commit()
            user = cursor.execute('SELECT * FROM users WHERE username = ? AND role = "student"', (scholar_no,)).fetchone()
            conn.close()

            # Log the new student in
            session['user_id'] = user['id']
            session['username'] = scholar_no
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
            
    return render_template('student_login.html')

# Route: Admin Login
@app.route('/login/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ? AND role = "admin"', (username, password)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            return render_template('admin_login.html', error="Invalid Admin Username or Password.")
            
    return render_template('admin_login.html')

# Route: Logout
@app.route('/logout')
def logout():
    role = session.get('role')
    session.clear()
    if role == 'admin':
        return redirect(url_for('admin_login'))
    return redirect(url_for('student_login'))

# Route: Dashboard
@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM complaints", conn)
    conn.close()
    
    total = len(df)
    pending = len(df[df['status'] == 'Pending']) if not df.empty else 0
    in_progress = len(df[df['status'] == 'In Progress']) if not df.empty else 0
    resolved = len(df[df['status'] == 'Resolved']) if not df.empty else 0
    
    return render_template('dashboard.html', total=total, pending=pending, in_progress=in_progress, resolved=resolved)

# Route: Register Complaint Form
@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if request.method == 'POST':
        scholar_no = session.get('username')
        department = request.form.get('department', '').strip()
        building = request.form.get('building', '').strip()
        room_no = request.form.get('room_no', '').strip()
        category = request.form.get('category', '').strip()
        priority = request.form.get('priority', '').strip()
        problem = request.form.get('problem', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM complaints")
        count = cursor.fetchone()[0] + 1
        complaint_id = f"CMP{count:03d}"
        today_date = datetime.now().strftime('%Y-%m-%d')

        cursor.execute('''
            INSERT INTO complaints (complaint_id, student_name, department, building, room_no, category, problem, priority, status, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
        ''', (complaint_id, scholar_no, department, building, room_no, category, problem, priority, today_date))
        
        conn.commit()
        conn.close()
        return redirect(url_for('tickets'))

    return render_template('register.html')

# Route: All Tickets & Search
@app.route('/tickets')
@login_required
def tickets():
    search_query = request.args.get('search', '').strip()
    conn = get_db_connection()
    if search_query:
        tickets = conn.execute(
            'SELECT * FROM complaints WHERE complaint_id LIKE ? OR student_name LIKE ? ORDER BY id DESC',
            (f'%{search_query}%', f'%{search_query}%')
        ).fetchall()
    else:
        tickets = conn.execute('SELECT * FROM complaints ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('tickets.html', tickets=tickets, search_query=search_query)

# Route: Update Ticket Status (Admin Only)
@app.route('/update_status/<complaint_id>', methods=['POST'])
@login_required
@admin_required
def update_status(complaint_id):
    new_status = request.form.get('status')
    if new_status in ['Pending', 'In Progress', 'Resolved']:
        conn = get_db_connection()
        conn.execute('UPDATE complaints SET status = ? WHERE complaint_id = ?', (new_status, complaint_id))
        conn.commit()
        conn.close()
    return redirect(url_for('tickets'))

# Route: Reports
@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()
    df_complaints = pd.read_sql_query("SELECT * FROM complaints", conn)
    df_maint = pd.read_sql_query("SELECT * FROM maintenance", conn)
    conn.close()

    most_common_cat = 'N/A'
    if not df_complaints.empty and not df_complaints['category'].mode().empty:
        most_common_cat = df_complaints['category'].mode()[0]

    most_reported_bldg = 'N/A'
    if not df_complaints.empty and not df_complaints['building'].mode().empty:
        most_reported_bldg = df_complaints['building'].mode()[0]

    metrics = {
        'total_complaints': len(df_complaints),
        'pending': len(df_complaints[df_complaints['status'] == 'Pending']) if not df_complaints.empty else 0,
        'in_progress': len(df_complaints[df_complaints['status'] == 'In Progress']) if not df_complaints.empty else 0,
        'resolved': len(df_complaints[df_complaints['status'] == 'Resolved']) if not df_complaints.empty else 0,
        'total_cost': df_maint['cost'].sum() if not df_maint.empty else 0,
        'avg_cost': round(df_maint['cost'].mean(), 2) if not df_maint.empty else 0,
        'most_common_cat': most_common_cat,
        'most_reported_bldg': most_reported_bldg
    }

    return render_template('reports.html', metrics=metrics)

# API Route for charts
@app.route('/api/chart-data')
@login_required
def chart_data():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM complaints", conn)
    conn.close()

    return jsonify({
        'categories': df['category'].value_counts().to_dict() if not df.empty else {},
        'statuses': df['status'].value_counts().to_dict() if not df.empty else {},
        'buildings': df['building'].value_counts().to_dict() if not df.empty else {}
    })

# Route: Export CSV (Admin Only)
@app.route('/export')
@login_required
@admin_required
def export_csv():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM complaints", conn)
    conn.close()
    
    return Response(
        df.to_csv(index=False),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=complaints_report.csv"}
    )

if __name__ == '__main__':
    init_db()
    app.run(debug=True)