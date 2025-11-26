import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from datetime import datetime, date, time
import pandas as pd
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from sqlalchemy import or_
from datetime import timedelta
import io


load_dotenv()          

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key')

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:0987@localhost:5432/student_attendance')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    course = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    confirmed = db.Column(db.Boolean, default=False)
    confirmation_date = db.Column(db.DateTime, nullable=True)
    registration_date = db.Column(db.DateTime, default=datetime.now)
    
    attendance = db.relationship("Attendance", backref="student", lazy=True)

    def __repr__(self):
        return f"<Student {self.student_id} - {self.name}>"

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=date.today)
    time = db.Column(db.Time, default=lambda: datetime.now().time())
    #time = db.Column(db.Time, nullable=False) 
    time_in = db.Column(db.Time, default=lambda: datetime.now().time())
    time_out = db.Column(db.Time, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Present')
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)

# Authentication Decorators
def login_required_student(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'student_id' not in session:
            flash("Please login as student first.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def login_required_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session:
            flash("Please login as admin first.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            student_id = request.form['student_id'].strip()
            name = request.form['name'].strip()
            course = request.form['course'].strip()
            email = request.form['email'].strip().lower()
            password = request.form['password']
            re_password = request.form['re_password']
            gender = request.form['gender']

            if password != re_password:
                flash("Passwords do not match!", "danger")
                return redirect(url_for("register"))

            if Student.query.filter_by(email=email).first():
                flash("Email already registered!", "danger")
                return redirect(url_for("register"))

            if Student.query.filter_by(student_id=student_id).first():
                flash("Student ID already exists!", "danger")
                return redirect(url_for("register"))

            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

            new_student = Student(
                student_id=student_id,
                name=name,
                course=course,
                email=email,
                password=hashed_password,
                gender=gender,
                confirmed=False
            )
            
            db.session.add(new_student)
            db.session.commit()
            
            flash("Registration submitted. Wait for admin confirmation.", "success")
            print(f"New student registered: {name} ({email})")
            return redirect(url_for("login"))

        except Exception as e:
            db.session.rollback()
            flash("Registration failed. Please try again.", "danger")
            print(f"Registration error: {str(e)}")
            return redirect(url_for("register"))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form['role']
        username = request.form['username'].strip().lower()
        password = request.form['password']

        if role == "admin":
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                session['admin'] = True
                return redirect(url_for("admin_dashboard"))
            else:
                flash("Invalid admin credentials", "danger")

        elif role == "student":
            student = Student.query.filter_by(email=username).first()
            if student and bcrypt.check_password_hash(student.password, password):
                if not student.confirmed:
                    flash("Your account is pending admin approval", "warning")
                else:
                    session['student_id'] = student.id
                    return redirect(url_for("student_dashboard"))
            else:
                flash("Invalid credentials", "danger")

    return render_template('login.html')

@app.route('/admin')
@login_required_admin
def admin_dashboard():
    pending_students = Student.query.filter_by(confirmed=False).all()
    confirmed_students = Student.query.filter(Student.confirmed == True, Student.confirmation_date.isnot(None)).all()
    return render_template('admin_dashboard.html',
                         pending_students=pending_students,
                         confirmed_students=confirmed_students)
    
    print(f"Pending Students: {pending_students}")
    print(f"Confirmed Students: {confirmed_students}")
    
    return render_template('admin_dashboard.html',
                         pending_students=pending_students,
                         confirmed_students=confirmed_students)

@app.route('/confirm_student/<int:student_id>')
@login_required_admin
def confirm_student(student_id):
    try:
        student = Student.query.get_or_404(student_id)
        student.confirmed = True
        student.confirmation_date = datetime.now()
        db.session.commit()
        flash(f"{student.name} has been confirmed!", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to confirm student", "danger")
        print(f"Error confirming student: {str(e)}")
    
    return redirect(url_for("admin_dashboard"))

@app.route('/delete_student/<int:student_id>')
@login_required_admin
def delete_student(student_id):
    try:
        student = Student.query.get_or_404(student_id)
        db.session.delete(student)
        db.session.commit()
        flash("Student deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash("Failed to delete student", "danger")
        print(f"Error deleting student: {str(e)}")
    
    return redirect(url_for("admin_dashboard"))

@app.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
@login_required_admin
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            course = request.form['course'].strip()
            gender = request.form['gender']
            new_student_id = request.form.get('student_id', '').strip()
            new_email = request.form.get('email', '').strip().lower()

            # email unique?
            if new_email != student.email and Student.query.filter_by(email=new_email).first():
                flash("Email already registered!", "danger")
                return redirect(url_for("edit_student", student_id=student.id))
            # student_id unique?
            if new_student_id != student.student_id and Student.query.filter_by(student_id=new_student_id).first():
                flash("Student ID already exists!", "danger")
                return redirect(url_for("edit_student", student_id=student.id))

            student.name = name
            student.course = course
            student.gender = gender
            student.email = new_email
            student.student_id = new_student_id

            db.session.commit()
            flash("Student updated successfully!", "success")
            return redirect(url_for("admin_students"))
        except Exception as e:
            db.session.rollback()
            flash("Failed to update student", "danger")
            print(f"Error updating student: {str(e)}")

    return render_template('edit_student.html', student=student)


@app.route('/confirm_delete_student/<int:student_id>', methods=['GET', 'POST'])
@login_required_admin
def confirm_delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == 'POST':
        try:
            # Futa attendance zake kwanza (kama una cascade unaweza kuacha)
            Attendance.query.filter_by(student_id=student.id).delete()
            db.session.delete(student)
            db.session.commit()
            flash("Student deleted successfully!", "success")
            return redirect(url_for('admin_students'))
        except Exception as e:
            db.session.rollback()
            flash("Failed to delete student", "danger")
            print(f"Error deleting student: {str(e)}")
            return redirect(url_for('admin_students'))
    # GET -> onyesha confirm page
    return render_template('confirm_delete_student.html', student=student)


@app.route('/admin/students')
@login_required_admin
def admin_students():
    q = request.args.get('q', '').strip()
    status = request.args.get('status', 'all')

    query = Student.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Student.name.ilike(like),
                Student.email.ilike(like),
                Student.student_id.ilike(like),
                Student.course.ilike(like),
            )
        )
    if status == 'pending':
        query = query.filter_by(confirmed=False)
    elif status == 'confirmed':
        query = query.filter_by(confirmed=True)

    students = query.order_by(Student.registration_date.desc()).all()
    total = Student.query.count()
    pending_count = Student.query.filter_by(confirmed=False).count()
    confirmed_count = Student.query.filter_by(confirmed=True).count()

    return render_template(
        'admin_students.html',
        students=students,
        q=q,
        status=status,
        total=total,
        pending_count=pending_count,
        confirmed_count=confirmed_count
    )

@app.route("/admin/attendance")
@login_required_admin
def admin_attendance():
    today = date.today()

    students = Student.query.all()
    records = Attendance.query.filter_by(date=today).all()
    record_map = {r.student_id: r for r in records}

    attendance_list = []
    for student in students:
        if student.id in record_map:
            attendance_list.append({
                "name": student.name,
                "date": today,
                "status": record_map[student.id].status
            })
        else:
           
            attendance_list.append({
                "name": student.name,
                "date": today,
                "status": "Absent"
            })

    return render_template("admin_attendance.html", attendance=attendance_list)


@app.route('/admin/records')
@login_required_admin
def admin_records():
    # Get filter parameters from request
    student_id = request.args.get('student_id')
    period = request.args.get('period', 'daily')
    date_str = request.args.get('date')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Query records based on filters
    query = db.session.query(Attendance).join(Student)
    
    if student_id:
        query = query.filter(Student.student_id == student_id)
    
    try:
        if period == 'daily' and date_str:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == filter_date)
        elif period == 'weekly' and date_str:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_of_week = filter_date - timedelta(days=filter_date.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            query = query.filter(Attendance.date.between(start_of_week, end_of_week))
        elif period == 'monthly' and date_str:
            year_month = datetime.strptime(date_str, '%Y-%m').date()
            start_of_month = date(year_month.year, year_month.month, 1)
            end_of_month = date(year_month.year, year_month.month + 1, 1) - timedelta(days=1)
            query = query.filter(Attendance.date.between(start_of_month, end_of_month))
        elif period == 'yearly' and date_str:
            year = datetime.strptime(date_str, '%Y').date()
            start_of_year = date(year.year, 1, 1)
            end_of_year = date(year.year, 12, 31)
            query = query.filter(Attendance.date.between(start_of_year, end_of_year))
        elif period == 'custom' and start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date.between(start_date, end_date))
    except ValueError as e:
        flash("Invalid date format", "danger")
        return redirect(url_for('admin_records'))
    
    records = query.order_by(Attendance.date.desc()).all()
    
    return render_template('admin_records.html', records=records)

@app.route('/export/records/<period>')
@login_required_admin
def export_records(period):
    try:
        # Similar filtering logic as admin_records
        query = db.session.query(Attendance).join(Student)
        
        if period == 'daily':
            today = date.today()
            records = query.filter(Attendance.date == today).all()
            filename = f"attendance_daily_{today}.xlsx"
        elif period == 'weekly':
            today = date.today()
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            records = query.filter(Attendance.date.between(start_of_week, end_of_week)).all()
            filename = f"attendance_weekly_{start_of_week}_to_{end_of_week}.xlsx"
        elif period == 'monthly':
            today = date.today()
            start_of_month = date(today.year, today.month, 1)
            end_of_month = date(today.year, today.month + 1, 1) - timedelta(days=1)
            records = query.filter(Attendance.date.between(start_of_month, end_of_month)).all()
            filename = f"attendance_monthly_{today.year}_{today.month}.xlsx"
        elif period == 'yearly':
            today = date.today()
            start_of_year = date(today.year, 1, 1)
            end_of_year = date(today.year, 12, 31)
            records = query.filter(Attendance.date.between(start_of_year, end_of_year)).all()
            filename = f"attendance_yearly_{today.year}.xlsx"
        else:
            flash("Invalid export period", "danger")
            return redirect(url_for('admin_records'))
        
        # Prepare data for Excel
        data = [{
            "Date": record.date.strftime('%Y-%m-%d'),
            "Student ID": record.student.student_id,
            "Name": record.student.name,
            "Course": record.student.course,
            "Time In": record.time_in.strftime('%H:%M:%S') if record.time_in else 'N/A',
            "Time Out": record.time_out.strftime('%H:%M:%S') if record.time_out else 'N/A',
            "Status": record.status
        } for record in records]
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        df.to_excel(output, index=False)
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        flash(f"Failed to generate export: {str(e)}", "danger")
        print(f"Export error: {str(e)}")
        return redirect(url_for('admin_records'))

@app.route('/student_dashboard')
@login_required_student
def student_dashboard():
    student = Student.query.get(session['student_id'])
    if not student:
        session.clear()
        flash("Student not found", "danger")
        return redirect(url_for("login"))
    
    attendance = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.date.desc()).all()
    return render_template("student_dashboard.html", student=student, attendance=attendance)

@app.route('/mark_attendance')
@login_required_student
def mark_attendance():
    student = Student.query.get(session['student_id'])
    if not student or not student.confirmed:
        flash("You are not authorized to mark attendance", "danger")
        return redirect(url_for("student_dashboard"))
    
    today = date.today()
    existing_attendance = Attendance.query.filter_by(
        student_id=student.id,
        date=today
    ).first()
    
    if existing_attendance:
        flash("Attendance already marked today", "info")
    else:
        try:
            now = datetime.now()
            record = Attendance(
                student_id=student.id,
                date=today,
                time=now.time(),
                status="Present"
            )
            db.session.add(record)
            db.session.commit()
            flash("Attendance marked successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash("Failed to mark attendance", "danger")
            print(f"Error marking attendance: {str(e)}")
    
    return redirect(url_for("student_dashboard"))

@app.route('/download_attendance')
@login_required_admin
def download_attendance():
    try:
        records = Attendance.query.join(Student).order_by(Attendance.date.desc()).all()
        data = [{
            "Date": record.date.strftime('%Y-%m-%d'),
            "Time": record.time.strftime('%H:%M:%S'),
            "Student ID": record.student.student_id,
            "Name": record.student.name,
            "Course": record.student.course,
            "Status": record.status
        } for record in records]
        
        df = pd.DataFrame(data)
        filepath = "attendance_records.xlsx"
        df.to_excel(filepath, index=False)
        
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        flash("Failed to generate attendance report", "danger")
        print(f"Error generating report: {str(e)}")
        return redirect(url_for("admin_dashboard"))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# Error Handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)