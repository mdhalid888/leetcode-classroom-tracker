import os
import shutil
import subprocess
import pandas as pd
from app import app, db
from models import Student, Submission, DailySnapshot, Notification, WeeklyReport, parse_registration_number

def seed_classmates(replace=False):
    with app.app_context():
        if replace:
            print("Clearing all existing database records (Overwrite Mode)...")
            try:
                db.session.query(Submission).delete()
                db.session.query(DailySnapshot).delete()
                db.session.query(Notification).delete()
                db.session.query(WeeklyReport).delete()
                db.session.query(Student).delete()
                db.session.commit()
                print("Database records cleared successfully.")
            except Exception as e:
                db.session.rollback()
                print(f"Error clearing records, running fallback schema reset: {e}")
                db.drop_all()
                db.create_all()
                print("Database schema reset successfully.")
        
        uploads_dir = os.path.join(app.root_path, 'uploads')
        if not os.path.exists(uploads_dir):
            print("Uploads folder not found.")
            return
            
        files = os.listdir(uploads_dir)
        # Exclude lock files and temporary items
        xlsx_files = [f for f in files if f.endswith('.xlsx') and not f.startswith('~$') and not f.startswith('temp_')]
        
        if not xlsx_files:
            print("No Excel files found in uploads/ folder.")
            return
            
        total_added = 0
        for f in xlsx_files:
            file_path = os.path.join(uploads_dir, f)
            temp_path = os.path.join(uploads_dir, f"temp_{f}")
            
            # Determine dept and year from filename or default
            dept_from_filename = None
            year_from_filename = None
            
            # Check if name is like DEPT_YEAR.xlsx (e.g. IT_4.xlsx)
            name_without_ext = os.path.splitext(f)[0]
            if '_' in name_without_ext:
                parts = name_without_ext.split('_')
                if len(parts) == 2:
                    dept_from_filename = parts[0].strip().upper()
                    try:
                        year_from_filename = int(parts[1].strip())
                    except ValueError:
                        pass
            
            print(f"Processing class file: {f} ...")
            try:
                # Cross-platform copy (works on both Windows and Linux without subprocess)
                shutil.copy2(file_path, temp_path)
                df = pd.read_excel(temp_path)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                print(f"Error copying/reading Excel {f}: {e}")
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                continue
                
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
                print(f"Skipping {f}: Column headers 'Name', 'Register Number', and 'LeetCode Username' not found.")
                continue
                
            added_count = 0
            updated_count = 0
            for index, row in df.iterrows():
                name = str(row.iloc[name_idx]).strip()
                reg_no = str(row.iloc[reg_idx]).strip()
                username = str(row.iloc[username_idx]).strip()
                
                if not name or not reg_no or not username or name == 'nan' or reg_no == 'nan' or username == 'nan':
                    continue
                    
                if reg_no.endswith('.0'):
                    reg_no = reg_no[:-2]
                    
                # Determine department and year
                dept = dept_from_filename
                year = year_from_filename
                
                # If not determined by filename, parse registration number
                if not dept or not year:
                    parsed_dept, parsed_year = parse_registration_number(reg_no)
                    if not dept:
                        dept = parsed_dept
                    if not year:
                        year = parsed_year
                
                # Check for duplicate
                existing = Student.query.filter(
                    (Student.register_number == reg_no) |
                    (Student.leetcode_username == username)
                ).first()
                
                if existing:
                    existing.name = name
                    existing.register_number = reg_no
                    existing.leetcode_username = username
                    existing.department = dept
                    existing.academic_year = year
                    existing.is_active = True
                    updated_count += 1
                else:
                    student = Student(
                        name=name,
                        register_number=reg_no,
                        leetcode_username=username,
                        department=dept,
                        academic_year=year,
                        is_active=True
                    )
                    db.session.add(student)
                    added_count += 1
                    
            db.session.commit()
            print(f"Loaded from {f} -> Added: {added_count}, Updated: {updated_count} (Class: {dept or 'Unknown'}_{year or 0}).")
            total_added += added_count
            
        print(f"Database sync complete. Total new students inserted: {total_added}.")

if __name__ == '__main__':
    seed_classmates()
