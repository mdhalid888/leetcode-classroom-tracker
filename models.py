from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

DEPT_MAP = {
    "104": "CSE",
    "205": "IT",
    "118": "CCE",
    "148": "AI ML",
    "149": "CYBER"
}

YEAR_MAP = {
    "23": 4,
    "24": 3,
    "25": 2
}

def parse_registration_number(reg_no):
    reg_str = str(reg_no).strip()
    if len(reg_str) < 12:
        return "Unknown", 0
    join_year_code = reg_str[4:6]
    dept_code = reg_str[6:9]
    return DEPT_MAP.get(dept_code, "Unknown"), YEAR_MAP.get(join_year_code, 0)

class Student(db.Model):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    register_number = db.Column(db.String(50), unique=True, nullable=False)
    leetcode_username = db.Column(db.String(100), unique=True, nullable=False)
    
    department = db.Column(db.String(50), nullable=True)
    academic_year = db.Column(db.Integer, nullable=True)
    
    total_solved = db.Column(db.Integer, default=0)
    easy_solved = db.Column(db.Integer, default=0)
    medium_solved = db.Column(db.Integer, default=0)
    hard_solved = db.Column(db.Integer, default=0)
    acceptance_rate = db.Column(db.Float, default=0.0)
    
    current_streak = db.Column(db.Integer, default=0)
    max_streak = db.Column(db.Integer, default=0)
    
    contest_rating = db.Column(db.Float, default=0.0)
    ranking = db.Column(db.Integer, default=0)
    avatar_url = db.Column(db.String(500), nullable=True)
    
    last_updated = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    submissions = db.relationship('Submission', backref='student', cascade='all, delete-orphan', lazy=True)
    snapshots = db.relationship('DailySnapshot', backref='student', cascade='all, delete-orphan', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'register_number': self.register_number,
            'leetcode_username': self.leetcode_username,
            'department': self.department,
            'academic_year': self.academic_year,
            'total_solved': self.total_solved,
            'easy_solved': self.easy_solved,
            'medium_solved': self.medium_solved,
            'hard_solved': self.hard_solved,
            'acceptance_rate': self.acceptance_rate,
            'current_streak': self.current_streak,
            'max_streak': self.max_streak,
            'contest_rating': self.contest_rating,
            'ranking': self.ranking,
            'avatar_url': self.avatar_url,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'is_active': self.is_active
        }

class Submission(db.Model):
    __tablename__ = 'submissions'
    
    id = db.Column(db.String(100), primary_key=True)  # Using LeetCode submission ID as primary key to prevent duplicates
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    title_slug = db.Column(db.String(255), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'title': self.title,
            'title_slug': self.title_slug,
            'difficulty': self.difficulty,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class DailySnapshot(db.Model):
    __tablename__ = 'daily_snapshots'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    
    total_solved = db.Column(db.Integer, default=0)
    easy_solved = db.Column(db.Integer, default=0)
    medium_solved = db.Column(db.Integer, default=0)
    hard_solved = db.Column(db.Integer, default=0)
    
    daily_solves = db.Column(db.Integer, default=0)  # Number of solves on this day
    
    __table_args__ = (db.UniqueConstraint('student_id', 'date', name='_student_date_uc'),)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'date': self.date.isoformat() if self.date else None,
            'total_solved': self.total_solved,
            'easy_solved': self.easy_solved,
            'medium_solved': self.medium_solved,
            'hard_solved': self.hard_solved,
            'daily_solves': self.daily_solves
        }

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class WeeklyReport(db.Model):
    __tablename__ = 'weekly_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    week_start = db.Column(db.Date, nullable=False, unique=True)
    
    top_solver = db.Column(db.String(100))        # Name of student who solved the most
    most_active = db.Column(db.String(100))       # Name of student who solved most days
    problems_solved = db.Column(db.Integer, default=0) # Total problems solved by class
    average_solves = db.Column(db.Float, default=0.0)   # Average problems solved per student
    inactive_members = db.Column(db.Text)          # Comma-separated names of inactive students
    top_improvement = db.Column(db.String(100))   # Student who grew solved count by most

    def to_dict(self):
        return {
            'id': self.id,
            'week_start': self.week_start.isoformat() if self.week_start else None,
            'top_solver': self.top_solver,
            'most_active': self.most_active,
            'problems_solved': self.problems_solved,
            'average_solves': self.average_solves,
            'inactive_members': self.inactive_members,
            'top_improvement': self.top_improvement
        }

class DailyTask(db.Model):
    __tablename__ = 'daily_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    problem_number = db.Column(db.String(50), nullable=True)
    problem_name = db.Column(db.String(255), nullable=False)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'problem_number': self.problem_number,
            'problem_name': self.problem_name,
            'date': self.date.isoformat() if self.date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
