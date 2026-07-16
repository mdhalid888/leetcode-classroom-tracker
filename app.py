import os
import io
import threading
import calendar
from datetime import datetime, date, timezone, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session, g
from models import db, Student, Submission, DailySnapshot, Notification, WeeklyReport
from scheduler import init_scheduler, run_update_task, update_status, generate_weekly_report
from leetcode import fetch_leetcode_data, parse_submission_calendar
from flask_cors import CORS

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'lc-classroom-tracker-secret-1234')

# Dynamic database configuration (supports Render persistent disk)
db_url = os.environ.get('DATABASE_URL')
if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
else:
    if os.path.exists('/data'):
        db_url = 'sqlite:////data/database.db'
    else:
        db_url = 'sqlite:///database.db'
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 280
}

db.init_app(app)
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-Admin-Auth", "Authorization", "Accept", "Origin"]
}}, supports_credentials=False)

# Helper function for human-readable time difference
def time_ago(dt):
    if not dt:
        return "Never"
    now = datetime.now()
    diff = now - dt
    
    if diff.days > 0:
        if diff.days == 1:
            return "1 day ago"
        return f"{diff.days} days ago"
        
    seconds = diff.seconds
    hours = seconds // 3600
    if hours > 0:
        if hours == 1:
            return "1 hour ago"
        return f"{hours} hours ago"
        
    minutes = seconds // 60
    if minutes > 0:
        if minutes == 1:
            return "1 min ago"
        return f"{minutes} mins ago"
        
    return "just now"

@app.template_filter('time_ago')
def time_ago_filter(dt):
    if not dt:
        return "Never"
    return time_ago(dt)

# Fetch Daily Challenge Helper
def fetch_daily_challenge():
    url = "https://leetcode.com/graphql"
    query = """
    query questionOfToday {
      activeDailyCodingChallengeQuestion {
        link
        question {
          title
          titleSlug
          difficulty
        }
      }
    }
    """
    try:
        import requests
        res = requests.post(url, json={"query": query}, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code == 200:
            q_data = res.json().get("data", {}).get("activeDailyCodingChallengeQuestion", {})
            q = q_data.get("question", {})
            if q:
                return {
                    "title": q.get("title"),
                    "title_slug": q.get("titleSlug"),
                    "difficulty": q.get("difficulty")
                }
    except Exception as e:
        print(f"Error fetching daily challenge: {e}")
    # Default placeholder
    return {
        "title": "Two Sum",
        "title_slug": "two-sum",
        "difficulty": "Easy"
    }

# ROUTES

@app.before_request
def require_login():
    # Bypass all API endpoints
    if request.path.startswith('/api/'):
        return
        
    # 1. Admin endpoints protection
    if request.path.startswith('/admin') and request.endpoint != 'admin_login':
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return # Skip student check for admin
        
    # Set current student if session exists, otherwise None
    student_id = session.get('student_id')
    if student_id:
        g.current_student = Student.query.get(student_id)
    else:
        g.current_student = None

@app.route('/login', methods=['GET', 'POST'])
def login_route():
    if 'student_id' in session:
        student = Student.query.get(session['student_id'])
        if student:
            return redirect(url_for('dashboard'))
            
    if request.method == 'POST':
        reg_no = request.form.get('register_number', '').strip()
        if reg_no.endswith('.0'):
            reg_no = reg_no[:-2]
            
        student = Student.query.filter_by(register_number=reg_no).first()
        if student:
            session['student_id'] = student.id
            flash(f"Welcome back, {student.name}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Registration number not found in database. Please contact your instructor/administrator.", "error")
            return redirect(url_for('login_route'))
            
    return render_template('login.html')

@app.route('/logout')
def logout_route():
    session.pop('student_id', None)
    flash("You have successfully logged out.", "success")
    return redirect(url_for('login_route'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('is_admin'):
        return redirect(url_for('admin_view'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if email == 'test456@gmail.com' and password == 'admin456@':
            session['is_admin'] = True
            flash("Admin login successful!", "success")
            return redirect(url_for('admin_view'))
        else:
            flash("Invalid admin credentials.", "error")
            return redirect(url_for('admin_login'))
            
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash("Admin logged out successfully.", "success")
    return redirect(url_for('admin_login'))

@app.route('/')
def dashboard():
    class_dept = g.current_student.department if g.current_student else 'ALL'
    class_year = g.current_student.academic_year if g.current_student else 'ALL'
    
    # Filter students in class
    query = Student.query.filter_by(is_active=True)
    if class_dept != 'ALL':
        query = query.filter_by(department=class_dept)
    if class_year != 'ALL':
        try:
            query = query.filter_by(academic_year=int(class_year))
        except ValueError:
            pass
            
    classmates = query.all()
    total_students = len(classmates)
    classmate_ids = [s.id for s in classmates]
    
    # Calculate classroom aggregates for classmates
    total_solves = 0
    if classmate_ids:
        total_solves = db.session.query(db.func.sum(Student.total_solved)).filter(Student.id.in_(classmate_ids)).scalar() or 0
    
    # Today's solves for classmates (unique problems solved today in IST)
    today_date = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    today_solves = 0
    
    # Calculate IST today boundaries in UTC
    ist_start = datetime(today_date.year, today_date.month, today_date.day, 0, 0, 0) - timedelta(hours=5, minutes=30)
    ist_end = datetime(today_date.year, today_date.month, today_date.day, 23, 59, 59) - timedelta(hours=5, minutes=30)
    
    if classmate_ids:
        # Sum of unique solved problems today per classmate
        today_solves = db.session.query(Submission.student_id, Submission.title_slug).filter(
            Submission.student_id.in_(classmate_ids),
            Submission.timestamp >= ist_start,
            Submission.timestamp <= ist_end
        ).distinct().count()
    
    # Top 5 solvers for class leaderboard snippet
    top_query = Student.query.filter_by(is_active=True)
    if class_dept != 'ALL':
        top_query = top_query.filter_by(department=class_dept)
    if class_year != 'ALL':
        try:
            top_query = top_query.filter_by(academic_year=int(class_year))
        except ValueError:
            pass
    top_students = top_query.order_by(Student.total_solved.desc()).limit(5).all()
    # Add dynamic unique today's solves to top students
    for student in top_students:
        student.today_solves = db.session.query(Submission.title_slug).filter(
            Submission.student_id == student.id,
            Submission.timestamp >= ist_start,
            Submission.timestamp <= ist_end
        ).distinct().count()

    # Recent submissions feed for class
    recent_submissions = []
    if classmate_ids:
        recent_submissions = Submission.query.filter(Submission.student_id.in_(classmate_ids)).order_by(Submission.timestamp.desc()).limit(25).all()
    for sub in recent_submissions:
        sub.time_ago = time_ago(sub.timestamp)

    # Notifications feed for class
    raw_notifications = Notification.query.order_by(Notification.timestamp.desc()).limit(60).all()
    notifications = []
    classmate_names = {s.name for s in classmates}
    for notif in raw_notifications:
        if any(name in notif.content for name in classmate_names) or "Weekly Report" in notif.content:
            notifications.append(notif)
            if len(notifications) >= 15:
                break
    for notif in notifications:
        notif.time_ago = time_ago(notif.timestamp)

    # Weekly report summary
    latest_weekly_report = WeeklyReport.query.order_by(WeeklyReport.week_start.desc()).first()

    # Daily challenge details
    daily_challenge = fetch_daily_challenge()
    
    # Count of classmates who completed the daily challenge today
    challenge_completed_count = 0
    if classmate_ids:
        challenge_completed_count = db.session.query(Submission.student_id).filter(
            Submission.student_id.in_(classmate_ids),
            Submission.title_slug == daily_challenge['title_slug'],
            db.func.date(Submission.timestamp) == today_date
        ).distinct().count()

    return render_template(
        'dashboard.html',
        total_students=total_students,
        total_solves=total_solves,
        today_solves=today_solves,
        top_students=top_students,
        recent_submissions=recent_submissions,
        notifications=notifications,
        weekly_report=latest_weekly_report,
        daily_challenge=daily_challenge,
        challenge_completed_count=challenge_completed_count
    )

@app.route('/leaderboard')
def leaderboard_view():
    active_filter = request.args.get('filter', 'overall')
    
    default_dept = 'ALL'
    default_year = 'ALL'
    if g.current_student:
        default_dept = g.current_student.department
        default_year = str(g.current_student.academic_year)
        
    dept = request.args.get('dept', default_dept).strip().upper()
    year = request.args.get('year', default_year).strip()
    
    query = Student.query.filter_by(is_active=True)
    if dept != 'ALL':
        query = query.filter_by(department=dept)
    if year != 'ALL':
        try:
            query = query.filter_by(academic_year=int(year))
        except ValueError:
            pass
            
    students = query.all()
    
    today_val = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    seven_days_ago = today_val - timedelta(days=7)
    thirty_days_ago = today_val - timedelta(days=30)
    
    # Calculate IST today boundaries in UTC
    ist_start = datetime(today_val.year, today_val.month, today_val.day, 0, 0, 0) - timedelta(hours=5, minutes=30)
    ist_end = datetime(today_val.year, today_val.month, today_val.day, 23, 59, 59) - timedelta(hours=5, minutes=30)
    
    # Dynamically inject temporary variables for sorting/rendering
    for s in students:
        s.today_solves = db.session.query(Submission.title_slug).filter(
            Submission.student_id == s.id,
            Submission.timestamp >= ist_start,
            Submission.timestamp <= ist_end
        ).distinct().count()
        
        weekly_snaps = DailySnapshot.query.filter(
            DailySnapshot.student_id == s.id,
            DailySnapshot.date >= seven_days_ago
        ).all()
        s.weekly_solves = sum(snap.daily_solves for snap in weekly_snaps)
        
        monthly_snaps = DailySnapshot.query.filter(
            DailySnapshot.student_id == s.id,
            DailySnapshot.date >= thirty_days_ago
        ).all()
        s.monthly_solves = sum(snap.daily_solves for snap in monthly_snaps)
        s.time_ago = time_ago(s.last_updated) if s.last_updated else "Never"
        
    # Sort students according to active filter
    if active_filter == 'today':
        students.sort(key=lambda x: x.today_solves, reverse=True)
    elif active_filter == 'week':
        students.sort(key=lambda x: x.weekly_solves, reverse=True)
    elif active_filter == 'month':
        students.sort(key=lambda x: x.monthly_solves, reverse=True)
    elif active_filter == 'easy':
        students.sort(key=lambda x: x.easy_solved, reverse=True)
    elif active_filter == 'medium':
        students.sort(key=lambda x: x.medium_solved, reverse=True)
    elif active_filter == 'hard':
        students.sort(key=lambda x: x.hard_solved, reverse=True)
    elif active_filter == 'acceptance':
        students.sort(key=lambda x: x.acceptance_rate, reverse=True)
    elif active_filter == 'rating':
        students.sort(key=lambda x: x.contest_rating, reverse=True)
    else: # overall
        students.sort(key=lambda x: x.total_solved, reverse=True)
        
    return render_template(
        'leaderboard.html',
        students=students,
        active_filter=active_filter,
        active_dept=dept,
        active_year=year
    )

@app.route('/student/<int:student_id>')
def student_profile(student_id):
    student = Student.query.get_or_404(student_id)
    
    # Class Rank
    all_students = Student.query.filter_by(is_active=True).order_by(Student.total_solved.desc()).all()
    class_rank = next((idx + 1 for idx, s in enumerate(all_students) if s.id == student.id), "-")
    
    # Submissions
    submissions = Submission.query.filter_by(student_id=student.id).order_by(Submission.timestamp.desc()).limit(20).all()
    for sub in submissions:
        sub.time_ago = time_ago(sub.timestamp)
        
    # Today, weekly, monthly solves
    today_val = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    
    # Calculate IST today boundaries in UTC
    ist_start = datetime(today_val.year, today_val.month, today_val.day, 0, 0, 0) - timedelta(hours=5, minutes=30)
    ist_end = datetime(today_val.year, today_val.month, today_val.day, 23, 59, 59) - timedelta(hours=5, minutes=30)
    
    today_solves = db.session.query(Submission.title_slug).filter(
        Submission.student_id == student.id,
        Submission.timestamp >= ist_start,
        Submission.timestamp <= ist_end
    ).distinct().count()
    
    weekly_snaps = DailySnapshot.query.filter(
        DailySnapshot.student_id == student.id,
        DailySnapshot.date >= today_val - timedelta(days=7)
    ).all()
    weekly_solves = sum(snap.daily_solves for snap in weekly_snaps)
    
    monthly_snaps = DailySnapshot.query.filter(
        DailySnapshot.student_id == student.id,
        DailySnapshot.date >= today_val - timedelta(days=30)
    ).all()
    monthly_solves = sum(snap.daily_solves for snap in monthly_snaps)

def get_student_graph_data(student, today_val):
    dates = [today_val - timedelta(days=i) for i in range(30)]
    snaps = [DailySnapshot.query.filter_by(student_id=student.id, date=d).first() for d in dates]
    
    anchors = []
    for i in range(30):
        if i == 0:
            anchors.append((0, student.total_solved))
        elif snaps[i] and snaps[i].total_solved > 0:
            anchors.append((i, snaps[i].total_solved))
            
    counts = [0] * 30
    
    for idx in range(len(anchors) - 1):
        L, val_L = anchors[idx]
        R, val_R = anchors[idx+1]
        
        sum_solves = 0
        for j in range(L, R):
            if snaps[j]:
                sum_solves += snaps[j].daily_solves
                
        diff = val_L - val_R
        
        current_val = val_L
        for j in range(L, R):
            counts[j] = int(round(current_val))
            daily_s = snaps[j].daily_solves if snaps[j] else 0
            if sum_solves > 0 and diff > 0:
                current_val -= daily_s * (diff / sum_solves)
            else:
                current_val -= diff / (R - L)
                
    last_idx, last_val = anchors[-1]
    counts[last_idx] = last_val
    current_val = last_val
    for j in range(last_idx + 1, 30):
        daily_s = snaps[j-1].daily_solves if snaps[j-1] else 0
        current_val = max(0, current_val - daily_s)
        counts[j] = int(round(current_val))
        
    graph_dates = [d.strftime('%b %d') for d in reversed(dates)]
    graph_counts = list(reversed(counts))
    return graph_dates, graph_counts

    # 1. Reconstruct past 30 days progress graph data
    graph_dates, graph_counts = get_student_graph_data(student, today_val)

    # 2. Reconstruct Heatmap Data (371 cells / 53 weeks)
    start_date = today_val - timedelta(days=364)
    # Align to Sunday
    start_date -= timedelta(days=(start_date.weekday() + 1) % 7)
    
    # Load all snapshots of student to cache dates lookup
    all_snaps = DailySnapshot.query.filter_by(student_id=student.id).all()
    snap_map = {snap.date: snap.daily_solves for snap in all_snaps}
    
    heatmap_days = []
    curr = start_date
    while len(heatmap_days) < 371:
        count = snap_map.get(curr, 0)
        cell_class = "cell-empty"
        if count > 0:
            if count <= 2: cell_class = "cell-lvl1"
            elif count <= 5: cell_class = "cell-lvl2"
            elif count <= 10: cell_class = "cell-lvl3"
            else: cell_class = "cell-lvl4"
            
        tooltip = f"{count} solves on {curr.strftime('%b %d, %Y')}"
        heatmap_days.append({
            'date': curr,
            'class': cell_class,
            'tooltip': tooltip
        })
        curr += timedelta(days=1)
        
    return render_template(
        'student.html',
        student=student,
        class_rank=class_rank,
        submissions=submissions,
        today_solves=today_solves,
        weekly_solves=weekly_solves,
        monthly_solves=monthly_solves,
        graph_dates=graph_dates,
        graph_counts=graph_counts,
        heatmap_days=heatmap_days,
        heatmap_start_date=start_date.strftime('%B %d, %Y'),
        heatmap_end_date=today_val.strftime('%B %d, %Y')
    )

@app.route('/compare')
def compare_view():
    default_dept = 'ALL'
    default_year = 'ALL'
    if g.current_student:
        default_dept = g.current_student.department
        default_year = str(g.current_student.academic_year)
        
    dept = request.args.get('dept', default_dept).strip().upper()
    year = request.args.get('year', default_year).strip()
    
    query = Student.query.filter_by(is_active=True)
    if dept != 'ALL':
        query = query.filter_by(department=dept)
    if year != 'ALL':
        try:
            query = query.filter_by(academic_year=int(year))
        except ValueError:
            pass
            
    all_students = query.order_by(Student.name).all()
    s1_id = request.args.get('s1')
    s2_id = request.args.get('s2')
    
    s1 = None
    s2 = None
    if s1_id and s2_id:
        s1 = Student.query.get(s1_id)
        s2 = Student.query.get(s2_id)
        
    # Ensure selected students are always present in the select options
    if s1 and s1 not in all_students:
        all_students.append(s1)
    if s2 and s2 not in all_students:
        all_students.append(s2)
    all_students.sort(key=lambda x: x.name)
        
    return render_template(
        'compare.html',
        all_students=all_students,
        s1=s1,
        s2=s2,
        active_dept=dept,
        active_year=year
    )

@app.route('/attendance')
def attendance_view():
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)
    
    num_days = calendar.monthrange(year, month)[1]
    days = list(range(1, num_days + 1))
    month_name = f"{calendar.month_name[month]} {year}"
    
    class_dept = g.current_student.department if g.current_student else 'ALL'
    class_year = g.current_student.academic_year if g.current_student else 'ALL'
    
    query = Student.query.filter_by(is_active=True)
    if class_dept != 'ALL':
        query = query.filter_by(department=class_dept)
    if class_year != 'ALL':
        try:
            query = query.filter_by(academic_year=int(class_year))
        except ValueError:
            pass
    students = query.order_by(Student.name).all()
    
    attendance_records = []
    for s in students:
        # Load all snapshots for this student in the target month/year
        snapshots = DailySnapshot.query.filter(
            DailySnapshot.student_id == s.id,
            db.extract('year', DailySnapshot.date) == year,
            db.extract('month', DailySnapshot.date) == month
        ).all()
        
        snap_map = {snap.date.day: snap.daily_solves for snap in snapshots}
        
        days_solved = []
        total_solves_this_month = 0
        active_days_count = 0
        
        for d in days:
            # Check if this day is in the future (upcoming) relative to IST today
            is_upcoming = False
            if year > today.year:
                is_upcoming = True
            elif year == today.year:
                if month > today.month:
                    is_upcoming = True
                elif month == today.month:
                    if d > today.day:
                        is_upcoming = True
                        
            solves = snap_map.get(d, 0)
            if solves > 0:
                days_solved.append('solved')
                total_solves_this_month += solves
                active_days_count += 1
            elif is_upcoming:
                days_solved.append('upcoming')
            else:
                days_solved.append('no_solves')
                
        solve_rate = round((active_days_count / num_days) * 100, 1) if num_days > 0 else 0
        
        attendance_records.append({
            'student': s,
            'days_solved': days_solved,
            'total_solves_this_month': total_solves_this_month,
            'solve_rate': solve_rate
        })
        
    months_list = [(i, calendar.month_name[i]) for i in range(1, 13)]
    years_list = list(range(today.year - 2, today.year + 1))
    
    return render_template(
        'attendance.html',
        days=days,
        month_name=month_name,
        attendance_records=attendance_records,
        active_month=month,
        active_year=year,
        months_list=months_list,
        years_list=years_list
    )

@app.route('/search')
def search_view():
    query = request.args.get('q', '').strip()
    students = []
    if query:
        # Search by name, username, or register number
        students = Student.query.filter(
            Student.is_active == True,
            (Student.name.like(f"%{query}%")) | 
            (Student.leetcode_username.like(f"%{query}%")) | 
            (Student.register_number.like(f"%{query}%"))
        ).all()
        
    return render_template('search.html', students=students, query=query)

@app.route('/admin')
def admin_view():
    total_students = Student.query.filter_by(is_active=True).count()
    last_run_formatted = update_status["last_run"].strftime("%B %d, %I:%M %p") if update_status["last_run"] else "Never"
    
    # Scan uploads/ folder for Excel sheets
    detected_files = []
    uploads_dir = os.path.join(app.root_path, 'uploads')
    if os.path.exists(uploads_dir):
        for f in os.listdir(uploads_dir):
            if f.endswith('.xlsx') and not f.startswith('~$') and not f.startswith('temp_'):
                name_without_ext = os.path.splitext(f)[0]
                dept = "Unknown"
                year = "Parsed"
                if '_' in name_without_ext:
                    parts = name_without_ext.split('_')
                    if len(parts) == 2:
                        dept = parts[0].strip().upper()
                        try:
                            year = int(parts[1].strip())
                        except:
                            pass
                detected_files.append({
                    'name': f,
                    'dept': dept,
                    'year': year
                })
                
    return render_template(
        'admin.html',
        total_students=total_students,
        update_status=update_status,
        last_run_formatted=last_run_formatted,
        detected_files=detected_files
    )

@app.route('/admin/scan-uploads', methods=['GET', 'POST'])
@app.route('/admin/scan_uploads', methods=['GET', 'POST'])
def scan_uploads():
    if request.method == 'POST':
        try:
            from seed_db import seed_classmates
            seed_classmates()
            flash("Class databases scanned and synced successfully.", "success")
        except Exception as e:
            flash(f"Error scanning uploads: {e}", "error")
    return redirect(url_for('admin_view'))

@app.route('/admin/upload-file', methods=['POST'])
def upload_file():
    if 'class_file' not in request.files:
        flash("No file selected for upload.", "error")
        return redirect(url_for('admin_view'))
        
    file = request.files['class_file']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for('admin_view'))
        
    if file and file.filename.endswith('.xlsx'):
        uploads_dir = os.path.join(app.root_path, 'uploads')
        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir)
            
        from werkzeug.utils import secure_filename
        safe_filename = secure_filename(file.filename)
        dest_path = os.path.join(uploads_dir, safe_filename)
        file.save(dest_path)
        
        try:
            from seed_db import seed_classmates
            seed_classmates()
            flash(f"File '{safe_filename}' uploaded and synced successfully.", "success")
        except Exception as e:
            flash(f"File uploaded, but database sync failed: {e}", "error")
    else:
        flash("Only Excel (.xlsx) files are allowed.", "error")
        
    return redirect(url_for('admin_view'))

# MANUAL SYNC ACTIONS (ASYNC THREAD)

@app.route('/admin/trigger-update', methods=['POST'])
def trigger_update():
    if update_status["in_progress"]:
        return jsonify({"status": "error", "message": "Update already in progress."})
        
    # Start thread
    thread = threading.Thread(target=run_update_task, args=(app,))
    thread.daemon = True
    thread.start()
    return jsonify({"status": "started"})

@app.route('/admin/update-status')
def get_update_status():
    status_copy = update_status.copy()
    if status_copy["last_run"]:
        status_copy["last_run"] = status_copy["last_run"].strftime("%B %d, %I:%M %p")
    return jsonify(status_copy)

# EXCEL STUDENT IMPORT

@app.route('/admin/upload', methods=['POST'])
def upload_excel():
    if 'file' not in request.files:
        flash("No file part found.", "error")
        return redirect(url_for('admin_view'))
        
    file = request.files['file']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for('admin_view'))
        
    if file and file.filename.endswith('.xlsx'):
        try:
            import pandas as pd
            
            # Save file to uploads folder
            uploads_dir = os.path.join(app.root_path, 'uploads')
            if not os.path.exists(uploads_dir):
                os.makedirs(uploads_dir)
            file_path = os.path.join(uploads_dir, 'students.xlsx')
            file.save(file_path)
            
            # Parse excel
            df = pd.read_excel(file_path)
            
            # Verify columns (case insensitive header match)
            headers = [str(col).strip().lower() for col in df.columns]
            
            name_idx = -1
            reg_idx = -1
            username_idx = -1
            
            for idx, h in enumerate(headers):
                if 'leetcode' in h or 'username' in h:
                    username_idx = idx
                elif 'register' in h or 'reg' in h:
                    reg_idx = idx
                elif 'name' in h:
                    name_idx = idx
                    
            if name_idx == -1 or reg_idx == -1 or username_idx == -1:
                flash("Excel must contain 'Name', 'Register Number', and 'LeetCode Username' columns.", "error")
                return redirect(url_for('admin_view'))
                
            added_count = 0
            updated_count = 0
            
            for index, row in df.iterrows():
                name = str(row.iloc[name_idx]).strip()
                reg_no = str(row.iloc[reg_idx]).strip()
                username = str(row.iloc[username_idx]).strip()
                
                # Basic validation
                if not name or not reg_no or not username or name == 'nan' or reg_no == 'nan' or username == 'nan':
                    continue
                    
                # Clean register number to integer-like or string
                if reg_no.endswith('.0'):
                    reg_no = reg_no[:-2]
                    
                # Check if student exists
                student = Student.query.filter(
                    (Student.register_number == reg_no) | 
                    (Student.leetcode_username == username)
                ).first()
                
                if student:
                    student.name = name
                    student.register_number = reg_no
                    student.leetcode_username = username
                    student.is_active = True
                    updated_count += 1
                else:
                    new_student = Student(
                        name=name,
                        register_number=reg_no,
                        leetcode_username=username,
                        is_active=True
                    )
                    db.session.add(new_student)
                    added_count += 1
                    
            db.session.commit()
            flash(f"Successfully uploaded: {added_count} students added, {updated_count} students updated.", "success")
            
        except Exception as e:
            flash(f"Error processing Excel: {e}", "error")
            
    else:
        flash("Invalid file format. Only .xlsx files are supported.", "error")
        
    return redirect(url_for('admin_view'))

@app.route('/admin/delete-file/<filename>', methods=['POST'])
def delete_file(filename):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(filename)
    file_path = os.path.join(app.root_path, 'uploads', safe_filename)
    
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            # Sync database after deletion by running seed_classmates
            from seed_db import seed_classmates
            seed_classmates()
            flash(f"File '{safe_filename}' deleted and classroom database synced successfully.", "success")
        except Exception as e:
            flash(f"Error deleting file: {e}", "error")
    else:
        flash("File not found.", "error")
        
    return redirect(url_for('admin_view'))

# EXPORTS & REPORTS DOWNLOAD

@app.route('/admin/download/<format>')
def download_report(format):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    dept = request.args.get('dept', 'ALL').strip().upper()
    year = request.args.get('year', 'ALL').strip()
    
    query = Student.query.filter_by(is_active=True)
    if dept != 'ALL':
        query = query.filter_by(department=dept)
    if year != 'ALL':
        try:
            query = query.filter_by(academic_year=int(year))
        except ValueError:
            pass
            
    students = query.order_by(Student.total_solved.desc()).all()
    
    # Calculate period solves for report headers (using unique solves today in IST)
    today_val = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    
    # Calculate IST today boundaries in UTC for unique solves count today
    ist_start = datetime(today_val.year, today_val.month, today_val.day, 0, 0, 0) - timedelta(hours=5, minutes=30)
    ist_end = datetime(today_val.year, today_val.month, today_val.day, 23, 59, 59) - timedelta(hours=5, minutes=30)
    
    for s in students:
        s.today_solves = db.session.query(Submission.title_slug).filter(
            Submission.student_id == s.id,
            Submission.timestamp >= ist_start,
            Submission.timestamp <= ist_end
        ).distinct().count()
        
        weekly_snaps = DailySnapshot.query.filter(
            DailySnapshot.student_id == s.id,
            DailySnapshot.date >= today_val - timedelta(days=7)
        ).all()
        s.weekly_solves = sum(snap.daily_solves for snap in weekly_snaps)
        
    # Generate dynamic titles and filename suffixes
    file_suffix = ""
    report_title = "LeetCode Classroom Tracker Report"
    if dept != 'ALL' or year != 'ALL':
        class_label = f"{dept if dept != 'ALL' else 'ALL'}_{year if year != 'ALL' else 'ALL'}"
        file_suffix = f"_{class_label}"
        report_title = f"LeetCode Report - {class_label}"
        
    if format == 'csv':
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            "Register Number", "Name", "LeetCode Username", "Total Solved", 
            "Easy", "Medium", "Hard", "Acceptance %", "Current Streak", 
            "Today's Solves", "Weekly Solves", "Contest Rating", "Last Updated"
        ])
        
        for s in students:
            writer.writerow([
                s.register_number, s.name, s.leetcode_username, s.total_solved,
                s.easy_solved, s.medium_solved, s.hard_solved, s.acceptance_rate,
                s.current_streak, s.today_solves, s.weekly_solves, s.contest_rating,
                s.last_updated.isoformat() if s.last_updated else "Never"
            ])
            
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"leetcode_report_{today_val.isoformat()}{file_suffix}.csv"
        )
        
    elif format == 'excel':
        # Create Excel file using pandas & xlsxwriter
        data_list = []
        for s in students:
            data_list.append({
                "Register Number": s.register_number,
                "Name": s.name,
                "LeetCode Username": s.leetcode_username,
                "Total Solved": s.total_solved,
                "Easy": s.easy_solved,
                "Medium": s.medium_solved,
                "Hard": s.hard_solved,
                "Acceptance %": s.acceptance_rate,
                "Current Streak": s.current_streak,
                "Today's Solves": s.today_solves,
                "Weekly Solves": s.weekly_solves,
                "Contest Rating": s.contest_rating,
                "Last Updated": s.last_updated.strftime("%Y-%m-%d %H:%M") if s.last_updated else "Never"
            })
            
        df = pd.DataFrame(data_list)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name="Classroom Solves", index=False)
            
            # Format workbook headers nicely using xlsxwriter formats
            workbook = writer.book
            worksheet = writer.sheets["Classroom Solves"]
            
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#1e293b',
                'font_color': '#ffffff',
                'border': 1
            })
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                # Auto-adjust column widths
                max_len = max(df[value].astype(str).map(len).max(), len(value)) + 3 if not df.empty else len(value) + 3
                worksheet.set_column(col_num, col_num, max_len)
                
        output.seek(0)
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"leetcode_report_{today_val.isoformat()}{file_suffix}.xlsx"
        )
        
    elif format == 'pdf':
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        
        output = io.BytesIO()
        doc = SimpleDocTemplate(
            output, 
            pagesize=letter, 
            rightMargin=25, 
            leftMargin=25, 
            topMargin=30, 
            bottomMargin=30
        )
        story = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#1e293b'),
            alignment=1, # Center
            spaceAfter=15
        )
        subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#64748b'),
            alignment=1,
            spaceAfter=25
        )
        
        story.append(Paragraph(report_title, title_style))
        story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y %I:%M %p')} | Total Solvers: {len(students)}", subtitle_style))
        
        # Table Columns: Reg Number, Name, Username, Total, Easy, Medium, Hard, Acceptance %, Current Streak, Contest Rating
        table_data = [
            ["Reg No", "Name", "Username", "Total", "Easy", "Med", "Hard", "Acceptance", "Streak", "Rating"]
        ]
        
        for s in students:
            table_data.append([
                str(s.register_number),
                str(s.name),
                f"@{s.leetcode_username}",
                str(s.total_solved),
                str(s.easy_solved),
                str(s.medium_solved),
                str(s.hard_solved),
                f"{s.acceptance_rate}%",
                f"{s.current_streak}d",
                str(int(s.contest_rating)) if s.contest_rating > 0 else "-"
            ])
            
        t = Table(table_data, colWidths=[65, 95, 75, 40, 35, 40, 35, 60, 45, 50])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('ALIGN', (1,1), (1,-1), 'LEFT'), # Name left
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('TOPPADDING', (0,0), (-1,0), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,1), (-1,-1), 5),
            ('TOPPADDING', (0,1), (-1,-1), 5),
        ]))
        
        story.append(t)
        doc.build(story)
        
        output.seek(0)
        return send_file(
            output,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"leetcode_report_{today_val.isoformat()}{file_suffix}.pdf"
        )
        
    flash("Invalid download format.", "error")
    return redirect(url_for('admin_view'))

# ==========================================
# REST API ENDPOINTS FOR DECOUPLED FRONTEND
# ==========================================

def get_current_student_from_request():
    student_id = request.args.get('student_id') or request.headers.get('X-Student-Id')
    if student_id:
        try:
            return Student.query.get(int(student_id))
        except ValueError:
            pass
    return None

def verify_admin_auth():
    auth_token = request.headers.get('X-Admin-Auth')
    return auth_token == 'admin456@'

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    reg_no = str(data.get('register_number', '')).strip()
    if not reg_no:
        return jsonify({'status': 'error', 'message': 'Register number is required.'}), 400
    
    student = Student.query.filter_by(register_number=reg_no, is_active=True).first()
    if not student:
        return jsonify({'status': 'error', 'message': 'Registration number not found or student is inactive.'}), 404
        
    return jsonify({
        'status': 'success',
        'student': student.to_dict()
    })

ADMIN_CREDENTIALS = {
    'test456@gmail.com': 'admin456@',
    # HODs
    'nitithod@nehrucolleges.com': 'itHod123$',
    'nitcsehod@nehrucolleges.com': 'cseHod123$',
    'nitccehod@nehrucolleges.com': 'cceHod123$',
    'nitaimlhod@nehrucolleges.com': 'aimlHod123$',
    'nitcshod@nehrucolleges.com': 'csHod123$',
    # Placements
    'nitplacements@nehrucolleges.com': 'nitplacements23$',
    'nitarunpatrick@nehrucolleges.com': 'nitArun123$',
    'nitjasonp@nehrucolleges.com': 'nitJason123$',
    'nititiv@nehrucolleges.com': 'nitIT123$',
    'nitcseiv@nehrucolleges.com': 'nitCSE123$'
}

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.json or {}
    email = str(data.get('email', '')).strip()
    password = str(data.get('password', '')).strip()
    
    if email in ADMIN_CREDENTIALS and ADMIN_CREDENTIALS[email] == password:
        return jsonify({
            'status': 'success',
            'admin_token': 'admin456@',
            'admin_email': email
        })
    return jsonify({'status': 'error', 'message': 'Invalid email or password.'}), 401

@app.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    dept = request.args.get('dept', '').strip().upper()
    year = request.args.get('year', '').strip()
    
    student = get_current_student_from_request()
    
    # Base query for classmates
    query_filter = Student.query.filter_by(is_active=True)
    
    # Apply department filter if not empty and not 'ALL'
    if dept and dept != 'ALL':
        query_filter = query_filter.filter_by(department=dept)
        class_dept = dept
    else:
        class_dept = 'ALL'
        
    # Apply academic year filter if not empty and not 'ALL'
    if year and year != 'ALL':
        try:
            val_year = int(year)
            query_filter = query_filter.filter_by(academic_year=val_year)
            class_year = str(val_year)
        except ValueError:
            class_year = 'ALL'
    else:
        class_year = 'ALL'
        
    classmates = query_filter.all()
    total_students = len(classmates)
    classmate_ids = [s.id for s in classmates]
    
    total_solves = 0
    if classmate_ids:
        total_solves = db.session.query(db.func.sum(Student.total_solved)).filter(Student.id.in_(classmate_ids)).scalar() or 0
    
    today_date = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    today_solves = 0
    
    ist_start = datetime(today_date.year, today_date.month, today_date.day, 0, 0, 0) - timedelta(hours=5, minutes=30)
    ist_end = datetime(today_date.year, today_date.month, today_date.day, 23, 59, 59) - timedelta(hours=5, minutes=30)
    
    if classmate_ids:
        today_solves = db.session.query(Submission.student_id, Submission.title_slug).filter(
            Submission.student_id.in_(classmate_ids),
            Submission.timestamp >= ist_start,
            Submission.timestamp <= ist_end
        ).distinct().count()
    
    top_query = Student.query.filter_by(is_active=True)
    if class_dept != 'ALL':
        top_query = top_query.filter_by(department=class_dept)
    if class_year != 'ALL':
        try:
            top_query = top_query.filter_by(academic_year=int(class_year))
        except ValueError:
            pass
            
    top_students = top_query.order_by(Student.total_solved.desc()).limit(5).all()
    top_students_list = []
    for s in top_students:
        s_dict = s.to_dict()
        s_dict['today_solves'] = db.session.query(Submission.title_slug).filter(
            Submission.student_id == s.id,
            Submission.timestamp >= ist_start,
            Submission.timestamp <= ist_end
        ).distinct().count()
        top_students_list.append(s_dict)

    recent_submissions = []
    if classmate_ids:
        recent_submissions = Submission.query.filter(Submission.student_id.in_(classmate_ids)).order_by(Submission.timestamp.desc()).limit(25).all()
    
    recent_list = []
    for sub in recent_submissions:
        sub_dict = sub.to_dict()
        sub_dict['time_ago'] = time_ago(sub.timestamp)
        sub_dict['student_name'] = sub.student.name
        recent_list.append(sub_dict)

    raw_notifications = Notification.query.order_by(Notification.timestamp.desc()).limit(60).all()
    notifications = []
    classmate_names = {s.name for s in classmates}
    for notif in raw_notifications:
        if any(name in notif.content for name in classmate_names) or "Weekly Report" in notif.content:
            notifications.append(notif)
            if len(notifications) >= 15:
                break
                
    notifications_list = []
    for notif in notifications:
        n_dict = notif.to_dict()
        n_dict['time_ago'] = time_ago(notif.timestamp)
        notifications_list.append(n_dict)

    latest_weekly_report = WeeklyReport.query.order_by(WeeklyReport.week_start.desc()).first()
    weekly_report_dict = latest_weekly_report.to_dict() if latest_weekly_report else None

    daily_challenge = fetch_daily_challenge()
    
    challenge_completed_count = 0
    if classmate_ids:
        challenge_completed_count = db.session.query(Submission.student_id).filter(
            Submission.student_id.in_(classmate_ids),
            Submission.title_slug == daily_challenge['title_slug'],
            db.func.date(Submission.timestamp) == today_date
        ).distinct().count()

    return jsonify({
        'status': 'success',
        'student': student.to_dict() if student else {'department': class_dept, 'academic_year': class_year},
        'total_students': total_students,
        'total_solves': total_solves,
        'today_solves': today_solves,
        'top_students': top_students_list,
        'recent_submissions': recent_list,
        'notifications': notifications_list,
        'weekly_report': weekly_report_dict,
        'daily_challenge': daily_challenge,
        'challenge_completed_count': challenge_completed_count
    })

@app.route('/api/leaderboard', methods=['GET'])
def api_leaderboard():
    active_filter = request.args.get('filter', 'overall')
    
    default_dept = 'ALL'
    default_year = 'ALL'
    student = get_current_student_from_request()
    if student:
        default_dept = student.department
        default_year = str(student.academic_year)
        
    dept = request.args.get('dept', default_dept).strip().upper()
    year = request.args.get('year', default_year).strip()
    
    query = Student.query.filter_by(is_active=True)
    if dept != 'ALL':
        query = query.filter_by(department=dept)
    if year != 'ALL':
        try:
            query = query.filter_by(academic_year=int(year))
        except ValueError:
            pass
            
    students = query.all()
    
    today_val = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    seven_days_ago = today_val - timedelta(days=7)
    thirty_days_ago = today_val - timedelta(days=30)
    
    ist_start = datetime(today_val.year, today_val.month, today_val.day, 0, 0, 0) - timedelta(hours=5, minutes=30)
    ist_end = datetime(today_val.year, today_val.month, today_val.day, 23, 59, 59) - timedelta(hours=5, minutes=30)
    
    students_list = []
    for s in students:
        s_dict = s.to_dict()
        s_dict['today_solves'] = db.session.query(Submission.title_slug).filter(
            Submission.student_id == s.id,
            Submission.timestamp >= ist_start,
            Submission.timestamp <= ist_end
        ).distinct().count()
        
        weekly_snaps = DailySnapshot.query.filter(
            DailySnapshot.student_id == s.id,
            DailySnapshot.date >= seven_days_ago
        ).all()
        s_dict['weekly_solves'] = sum(snap.daily_solves for snap in weekly_snaps)
        
        monthly_snaps = DailySnapshot.query.filter(
            DailySnapshot.student_id == s.id,
            DailySnapshot.date >= thirty_days_ago
        ).all()
        s_dict['monthly_solves'] = sum(snap.daily_solves for snap in monthly_snaps)
        s_dict['time_ago'] = time_ago(s.last_updated) if s.last_updated else "Never"
        students_list.append(s_dict)
        
    if active_filter == 'today':
        students_list.sort(key=lambda x: x['today_solves'], reverse=True)
    elif active_filter == 'week':
        students_list.sort(key=lambda x: x['weekly_solves'], reverse=True)
    elif active_filter == 'month':
        students_list.sort(key=lambda x: x['monthly_solves'], reverse=True)
    elif active_filter == 'easy':
        students_list.sort(key=lambda x: x['easy_solved'], reverse=True)
    elif active_filter == 'medium':
        students_list.sort(key=lambda x: x['medium_solved'], reverse=True)
    elif active_filter == 'hard':
        students_list.sort(key=lambda x: x['hard_solved'], reverse=True)
    elif active_filter == 'streak':
        students_list.sort(key=lambda x: x['current_streak'], reverse=True)
    elif active_filter == 'rating':
        students_list.sort(key=lambda x: x['contest_rating'], reverse=True)
    else:
        students_list.sort(key=lambda x: x['total_solved'], reverse=True)
        
    return jsonify({
        'status': 'success',
        'students': students_list,
        'active_filter': active_filter,
        'active_dept': dept,
        'active_year': year
    })

@app.route('/api/student/<int:student_id>', methods=['GET'])
def api_student_profile(student_id):
    student = Student.query.get_or_404(student_id)
    
    all_students = Student.query.filter_by(is_active=True).order_by(Student.total_solved.desc()).all()
    class_rank = next((idx + 1 for idx, s in enumerate(all_students) if s.id == student.id), "-")
    
    submissions = Submission.query.filter_by(student_id=student.id).order_by(Submission.timestamp.desc()).limit(20).all()
    subs_list = []
    for sub in submissions:
        sub_dict = sub.to_dict()
        sub_dict['time_ago'] = time_ago(sub.timestamp)
        subs_list.append(sub_dict)
        
    today_val = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    
    ist_start = datetime(today_val.year, today_val.month, today_val.day, 0, 0, 0) - timedelta(hours=5, minutes=30)
    ist_end = datetime(today_val.year, today_val.month, today_val.day, 23, 59, 59) - timedelta(hours=5, minutes=30)
    
    today_solves = db.session.query(Submission.title_slug).filter(
        Submission.student_id == student.id,
        Submission.timestamp >= ist_start,
        Submission.timestamp <= ist_end
    ).distinct().count()
    
    weekly_snaps = DailySnapshot.query.filter(
        DailySnapshot.student_id == student.id,
        DailySnapshot.date >= today_val - timedelta(days=7)
    ).all()
    weekly_solves = sum(snap.daily_solves for snap in weekly_snaps)
    
    monthly_snaps = DailySnapshot.query.filter(
        DailySnapshot.student_id == student.id,
        DailySnapshot.date >= today_val - timedelta(days=30)
    ).all()
    monthly_solves = sum(snap.daily_solves for snap in monthly_snaps)
    
    graph_dates, graph_counts = get_student_graph_data(student, today_val)
    
    one_year_ago = today_val - timedelta(days=365)
    year_snaps = DailySnapshot.query.filter(
        DailySnapshot.student_id == student.id,
        DailySnapshot.date >= one_year_ago
    ).order_by(DailySnapshot.date).all()
    
    heatmap_days = []
    for snap in year_snaps:
        heatmap_days.append({
            'date': snap.date.isoformat(),
            'count': snap.daily_solves
        })
        
    return jsonify({
        'status': 'success',
        'student': student.to_dict(),
        'class_rank': class_rank,
        'submissions': subs_list,
        'today_solves': today_solves,
        'weekly_solves': weekly_solves,
        'monthly_solves': monthly_solves,
        'graph_dates': graph_dates,
        'graph_counts': graph_counts,
        'heatmap_days': heatmap_days,
        'heatmap_start_date': one_year_ago.isoformat(),
        'heatmap_end_date': today_val.isoformat()
    })

@app.route('/api/compare', methods=['GET'])
def api_compare():
    default_dept = 'ALL'
    default_year = 'ALL'
    student = get_current_student_from_request()
    if student:
        default_dept = student.department
        default_year = str(student.academic_year)
        
    dept = request.args.get('dept', default_dept).strip().upper()
    year = request.args.get('year', default_year).strip()
    
    query = Student.query.filter_by(is_active=True)
    if dept != 'ALL':
        query = query.filter_by(department=dept)
    if year != 'ALL':
        try:
            query = query.filter_by(academic_year=int(year))
        except ValueError:
            pass
            
    all_students = query.order_by(Student.name).all()
    s1_id = request.args.get('s1')
    s2_id = request.args.get('s2')
    
    s1 = None
    s2 = None
    if s1_id and s2_id:
        s1 = Student.query.get(s1_id)
        s2 = Student.query.get(s2_id)
        
    if s1 and s1 not in all_students:
        all_students.append(s1)
    if s2 and s2 not in all_students:
        all_students.append(s2)
    all_students.sort(key=lambda x: x.name)
    
    all_students_dicts = [s.to_dict() for s in all_students]
    
    return jsonify({
        'status': 'success',
        'all_students': all_students_dicts,
        's1': s1.to_dict() if s1 else None,
        's2': s2.to_dict() if s2 else None,
        'active_dept': dept,
        'active_year': year
    })

@app.route('/api/attendance', methods=['GET'])
def api_attendance():
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)
    
    num_days = calendar.monthrange(year, month)[1]
    days = list(range(1, num_days + 1))
    month_name = f"{calendar.month_name[month]} {year}"
    
    class_dept = "IT"
    class_year = 4
    student = get_current_student_from_request()
    if student:
        class_dept = student.department
        class_year = student.academic_year
        
    students = Student.query.filter_by(department=class_dept, academic_year=class_year, is_active=True).order_by(Student.name).all()
    
    attendance_records = []
    for s in students:
        snapshots = DailySnapshot.query.filter(
            DailySnapshot.student_id == s.id,
            db.extract('year', DailySnapshot.date) == year,
            db.extract('month', DailySnapshot.date) == month
        ).all()
        
        snap_map = {snap.date.day: snap.daily_solves for snap in snapshots}
        
        days_solved = []
        total_solves_this_month = 0
        active_days_count = 0
        
        for d in days:
            is_upcoming = False
            if year > today.year:
                is_upcoming = True
            elif year == today.year:
                if month > today.month:
                    is_upcoming = True
                elif month == today.month:
                    if d > today.day:
                        is_upcoming = True
                        
            solves = snap_map.get(d, 0)
            if solves > 0:
                days_solved.append('solved')
                total_solves_this_month += solves
                active_days_count += 1
            elif is_upcoming:
                days_solved.append('upcoming')
            else:
                days_solved.append('no_solves')
                
        solve_rate = round((active_days_count / num_days) * 100, 1) if num_days > 0 else 0
        
        attendance_records.append({
            'student': s.to_dict(),
            'days_solved': days_solved,
            'total_solves_this_month': total_solves_this_month,
            'solve_rate': solve_rate
        })
        
    months_list = [(i, calendar.month_name[i]) for i in range(1, 13)]
    years_list = list(range(today.year - 2, today.year + 1))
    
    return jsonify({
        'status': 'success',
        'days': days,
        'month_name': month_name,
        'attendance_records': attendance_records,
        'active_month': month,
        'active_year': year,
        'months_list': months_list,
        'years_list': years_list
    })

@app.route('/api/admin/dashboard', methods=['GET'])
def api_admin_dashboard():
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized admin access.'}), 401
        
    active_students = Student.query.filter_by(is_active=True).count()
    last_updated_student = Student.query.order_by(Student.last_updated.desc()).first()
    last_updated = last_updated_student.last_updated.isoformat() if (last_updated_student and last_updated_student.last_updated) else "Never"
    
    # Query database for parsed classes and counts instead of ephemeral disk files
    classes_in_db = db.session.query(
        Student.department, 
        Student.academic_year, 
        db.func.count(Student.id)
    ).filter_by(is_active=True).group_by(Student.department, Student.academic_year).all()
    
    excel_files = []
    for dept, yr, count in classes_in_db:
        if dept:
            excel_files.append({
                'name': f"{dept}_{yr}.xlsx",
                'dept': dept,
                'year': yr if yr is not None else 'Unknown',
                'size': f"{count} Students"
            })
            
    curr_status = update_status()
    
    return jsonify({
        'status': 'success',
        'active_students': active_students,
        'last_updated': last_updated,
        'detected_files': excel_files,
        'update_status': curr_status
    })

@app.route('/api/admin/upload-file', methods=['POST'])
def api_admin_upload_file():
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized admin access.'}), 401
        
    if 'class_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part in request.'}), 400
        
    file = request.files['class_file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected.'}), 400
        
    if file and file.filename.endswith('.xlsx'):
        replace_db = request.form.get('replace', 'false') == 'true'
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        upload_dir = os.path.join(app.root_path, 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        if replace_db:
            # Clear all existing files in the uploads folder
            for f in os.listdir(upload_dir):
                if f.endswith('.xlsx'):
                    try:
                        os.remove(os.path.join(upload_dir, f))
                    except:
                        pass
                        
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        from seed_db import seed_classmates
        try:
            seed_classmates(replace=replace_db)
            return jsonify({'status': 'success', 'message': f"File '{filename}' uploaded and database successfully synchronized."})
        except Exception as e:
            return jsonify({'status': 'error', 'message': f"Error parsing uploaded Excel roster: {e}"}), 500
            
    return jsonify({'status': 'error', 'message': 'Unsupported file format. Only Excel (.xlsx) files are supported.'}), 400

@app.route('/api/admin/delete-file/<filename>', methods=['POST'])
def api_admin_delete_file(filename):
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized admin access.'}), 401
        
    dept = None
    year = None
    name_without_ext = filename.replace('.xlsx', '')
    if '_' in name_without_ext:
        parts = name_without_ext.split('_')
        if len(parts) == 2:
            dept = parts[0].strip().upper()
            try:
                year = int(parts[1].strip())
            except ValueError:
                pass
                
    try:
        deleted_count = 0
        if dept and year is not None:
            students = Student.query.filter_by(department=dept, academic_year=year).all()
            for s in students:
                db.session.delete(s)
            deleted_count = len(students)
            db.session.commit()
            
        from werkzeug.utils import secure_filename
        safe_filename = secure_filename(filename)
        file_path = os.path.join(app.root_path, 'uploads', safe_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            
        return jsonify({'status': 'success', 'message': f"Deleted class '{dept} - Year {year}' ({deleted_count} students) from database."})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f"Error deleting class: {e}"}), 500

@app.route('/api/admin/scan-uploads', methods=['POST'])
def api_admin_scan_uploads():
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized admin access.'}), 401
        
    try:
        from seed_db import seed_classmates
        seed_classmates()
        return jsonify({'status': 'success', 'message': "Roster scanner executed. All active classes successfully synchronized."})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f"Roster scanner failed: {e}"}), 500

@app.route('/api/admin/trigger-update', methods=['POST'])
def api_admin_trigger_update():
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized admin access.'}), 401
        
    threading.Thread(target=run_update_task, args=(app,)).start()
    return jsonify({'status': 'success', 'message': "LeetCode updates triggered in the background."})

@app.route('/api/admin/update-status', methods=['GET'])
def api_admin_update_status():
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized admin access.'}), 401
    return jsonify({
        'status': 'success',
        'update_status': update_status()
    })

@app.route('/api/health', methods=['GET'])
def api_health():
    db_status = "connected"
    try:
        db.session.execute(db.select(1))
    except Exception as e:
        db_status = f"error: {e}"
        
    return jsonify({
        "status": "online",
        "database": db_status,
        "server": "running"
    }), 200

# APP RUNNER & DB SETUP

# Create directories and seed database
with app.app_context():
    db.create_all()
    # Check if empty, and maybe inject dummy data helper if user wants, 
    # but leaving it empty for Excel import is cleaner.
    
    # Initialize background scheduler
    init_scheduler(app)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
