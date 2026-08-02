from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash
import razorpay
import csv
import pandas as pd
from reportlab.pdfgen import canvas
from datetime import datetime
from reportlab.lib.pagesizes import letter
import threading



app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
import os


import os

if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")

if not os.path.exists("static/gallery"):
    os.makedirs("static/gallery")


# ✅ create upload folder if not exists
if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")


import os
app.secret_key = os.getenv("SECRET_KEY", "fallback123")

# ---------------- DATABASE ----------------

# ✅ DATABASE CONFIG ONCE
db_url = os.getenv("DATABASE_URL")

db_url = os.getenv("DATABASE_URL")

print("DB URL:", db_url)   # ✅ DEBUG

if not db_url:
    print("❌ DATABASE_URL still not found")
    db_url = "sqlite:///fallback.db"   # TEMP fallback

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ---------------- MODELS ----------------
class Gallery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50))
    title = db.Column(db.String(200))
    image = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    capacity = db.Column(db.Integer, default=3)
    filled_slots = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))

    age = db.Column(db.Integer)      # ✅ ADD
    college = db.Column(db.String(100))

    pincode = db.Column(db.String(10))   # ✅ ADD
    state = db.Column(db.String(100))    # ✅ ADD
    district = db.Column(db.String(100)) # ✅ ADD
    place = db.Column(db.String(100))    # ✅ ADD

    batch_id = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    seat = db.Column(db.String(10))
    transaction_id = db.Column(db.String(100))
    payment_proof = db.Column(db.String(200))
    payment_status = db.Column(db.String(20), default="Pending")
    application_status = db.Column(db.String(20), default="Pending")
    completion_status = db.Column(db.String(20),default="In Progress")



# ---------------- ADMIN LOGIN ----------------
ADMIN_USER = "Tukaram"
#ADMIN_PASS_HASH = "PASTE_YOUR_HASH_HERE"
ADMIN_PASS = "#Samhita@1414"


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == ADMIN_USER and password == ADMIN_PASS:
            session['admin'] = True
            return redirect('/admin')
        else:
            return "Invalid Credentials ❌"

    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------------- HOME Stsus of Application ------------
    
@app.route("/check_status", methods=["POST"])
def check_status():

    data = request.get_json()
    query = data.get("query")

    # ✅ search using phone OR name (case-insensitive)
    student = Student.query.filter(
        (Student.phone == query) |
        (Student.name.ilike(f"%{query}%"))
    ).first()

    if not student:
        return {"status": "Not Found"}

    return {
        "status": student.application_status
    }
#--------------++++++====___
###++++++++++++++++++++_------=====-



# ---------------- REGISTER ----------------


from datetime import datetime
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'GET':
        return render_template(
            "register.html",
            batches=prepare_batches()
        )

    try:
        data = request.form
        file = request.files.get('payment_proof')

        seat = data.get('seat')
        gender = data.get('gender')

        filename = None
        if file and file.filename:
            filename = file.filename
            file.save(f"static/uploads/{filename}")

        batch_id_str = data.get('batch_id')

        if not batch_id_str:
            return "Please select a batch"

        batch_id = int(batch_id_str)
        batch = db.session.get(Batch, batch_id)

        if not batch:
            return "Invalid batch"

        if batch.filled_slots >= batch.capacity:
            return "Batch is full"

        male_count = Student.query.filter_by(
            batch_id=batch.id,
            gender="Male"
        ).count()

        female_count = Student.query.filter_by(
            batch_id=batch.id,
            gender="Female"
        ).count()

        if gender == "Male" and male_count >= 3:
            return "No seats available for Male"

        if gender == "Female" and female_count >= 3:
            return "No seats available for Female"

        # Safe age conversion
        try:
            age = int(
                data.get('age', '0')
                .replace(" Yrs", "")
                .strip()
            )
        except:
            age = 0

        student = Student(
            name=data.get('name'),
            email=data.get('email'),
            phone=data.get('phone'),
            age=age,
            college=data.get('college'),
            pincode=data.get('pincode'),
            state=data.get('state'),
            district=data.get('district'),
            place=data.get('place'),
            batch_id=batch.id,
            seat=seat,
            gender=gender,
            transaction_id=data.get('transaction_id'),
            payment_proof=filename,
            payment_status="Pending"
        )

        batch.filled_slots += 1

        db.session.add(student)
        db.session.commit()

        # Email
        threading.Thread(
            target=send_email,
            args=(
                student.email,
                "Training Application Received ✅"

                f"""
                Dear {student.name},

                Greetings from Amrutha Aarogya Kendra Ayurvedic Hospital.

                Thank you for applying for our Internship Program.
                We are pleased to inform you that your application has been successfully received.

                ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                     APPLICATION DETAILS
                ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                Applicant Name      : {student.name}
                Email Address       : {student.email}
                Mobile Number       : {student.phone}

                Age                 : {student.age}
                Gender              : {student.gender}

                College             : {student.college}

                Place               : {student.place}
                District            : {student.district}
                State               : {student.state}
                Pincode             : {student.pincode}

                Selected Internship : {student.seat}

                Transaction ID      : {student.transaction_id}
                Payment Status      : {student.payment_status}

                Application Status  : Under Review

                ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                Your application has been forwarded to our Internship Committee for verification.

                Once your documents and payment are verified, you will receive another email regarding your application status.

                Please keep this email for your records.

                If you have any questions, feel free to contact the Training & Internship Department.

                We appreciate your interest in training with Amrutha Aarogya Kendra Ayurvedic Hospital and wish you the very best.

                Warm Regards,

                Dr. Tukaram Umarani
                Ayurvedacharya

                Training & Internship Department
                Amrutha Aarogya Kendra Ayurvedic Hospital Kalloli
                """
                
            )
        ).start()

        return redirect('/success')

    except Exception as e:
        db.session.rollback()
        print("REGISTER ERROR:", str(e))
        return f"ERROR: {str(e)}"


##----------------------Batches------------------------------------------------------ 
"""def prepare_batches():
    batches = Batch.query.order_by(Batch.start_date).all()
    #grouped = {}
    result = []
    today = datetime.today().date()
    
    for b in batches:
        try:
            start = datetime.strptime(b.start_date, "%Y-%m-%d")
            end = datetime.strptime(b.end_date, "%Y-%m-%d")
        except:
            continue

        # ✅ skip past batches
        if end.date() < today:
            continue


        male_count = Student.query.filter_by(batch_id=b.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=b.id, gender="Female").count()

        grouped[month]["male"] += male_count
        grouped[month]["female"] += female_count

    result = []

    for month, data in grouped.items():

        male_left = max(0, 6 - data["male"])
        female_left = max(0, 6 - data["female"])

        # ✅ CORRECT LINE
        

        result.append({
            "id": data["ids"][0],
            "label": label,
            "male_left": male_left,
            "female_left": female_left
        })

    return result


"""

    #return render_template("register.html", batches=Batch.query.all())

# ---------------- SUCCESS ----------------
@app.route('/success')
def success():
    return render_template("success.html")

##------AI 
# ✅ IMPORT
from openai import OpenAI

# ✅ CLIENT
client = OpenAI(api_key="YOUR_API_KEY")


# ✅ SINGLE CHAT ROUTE (ONLY ONE ✅)
@app.route("/chat", methods=["POST"])
def chat():

    user_msg = request.json.get("message")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Answer ONLY from hospital training rules. If outside, say: Please contact hospital 📞"
            },
            {
                "role": "user",
                "content": user_msg
            }
        ]
    )

    return {
        "reply": response.choices[0].message.content
    }

# ---------------- ADMIN DASHBOARD ----------------
from datetime import datetime

@app.route('/admin')
def admin():

    if not session.get('admin'):
        return redirect('/login')

    today = datetime.today()

    all_batches = Batch.query.all()

    batches = []
    for b in batches:
        b.filled_slots = Student.query.filter_by(
            batch_id=b.id
        ).count()

    for b in all_batches:
        try:
            end_date = datetime.strptime(
                b.end_date,
                "%Y-%m-%d"
            )

            # Skip expired batches
            if end_date < today:
                continue

            b.start_display = datetime.strptime(
                b.start_date,
                "%Y-%m-%d"
            ).strftime("%d-%b-%Y")

            b.end_display = datetime.strptime(
                b.end_date,
                "%Y-%m-%d"
            ).strftime("%d-%b-%Y")

            batches.append(b)

        except:
            continue

    return render_template(
        "admin.html",
        students=Student.query.all(),
        batches=batches
    )

###-----------------------===---= All Candistes on Admin Portal
#=====___---------------+++
@app.route("/all_candidates")
def all_candidates():

    if not session.get('admin'):
        return redirect('/login')

    students = Student.query.order_by(Student.id.asc()).all()

    return render_template("all_candidates.html", students=students)


@app.route('/gallery_admin', methods=['GET', 'POST'])
def gallery_admin():

    if request.method == 'POST':

        category = request.form['category']
        title = request.form['title']

        file = request.files['image']

        filename = file.filename
        file.save(f"static/gallery/{filename}")

        img = Gallery(
            category=category,
            title=title,
            image=filename
        )

        db.session.add(img)
        db.session.commit()

    images = Gallery.query.all()

    return render_template("gallery_admin.html", images=images)

###########--------------------------- Seat Status--------------------
@app.route('/seat_status')
def seat_status():

    data = {}

    #batches = Batch.query.all()
    batches = Batch.query.order_by(Batch.start_date).all()

    for b in batches:
        male_count = Student.query.filter_by(batch_id=b.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=b.id, gender="Female").count()

        data[b.id] = {
            "male_left": 3 - male_count,
            "female_left": 3 - female_count
        }

    return jsonify(data)


# ---------------- ADD BATCH (NO OVERLAP) ----------------
@app.route('/add_batch', methods=['POST'])
def add_batch():
    if not session.get('admin'):
        return redirect('/login')

    start = request.form['start_date']
    end = request.form['end_date']

    start_date = datetime.strptime(start, "%Y-%m-%d")
    end_date = datetime.strptime(end, "%Y-%m-%d")

    for b in Batch.query.all():
        try:
            b_start = datetime.strptime(b.start_date, "%Y-%m-%d")
            b_end = datetime.strptime(b.end_date, "%Y-%m-%d")

            if not (end_date <= b_start or start_date >= b_end):
                return "❌ Overlapping batch not allowed"
        except:
            continue

    new_batch = Batch(
        start_date=start,
        end_date=end,
        capacity=int(request.form['capacity']),
        filled_slots=0
    )

    db.session.add(new_batch)
    db.session.commit()

    return redirect('/admin')

#--------- Auto generate Batches

import calendar
from datetime import datetime

#@app.route('/generate_batches')
"""def generate_batches():

    year = datetime.now().year

    for y in range(year, year + 2):   # ✅ current + next year
        for month in range(1, 13):

            last_day = calendar.monthrange(y, month)[1]

            start_date = f"{y}-{month:02d}-01"
            end_date = f"{y}-{month:02d}-{last_day}"

            # ✅ PREVENT DUPLICATES
            exists = Batch.query.filter_by(start_date=start_date).first()

            if not exists:
                db.session.add(Batch(
                    start_date=start_date,
                    end_date=end_date,
                    capacity=6,
                    filled_slots=0
                ))

    db.session.commit()

    return "✅ Batches generated successfully"
"""


# ---------------- AUTO GENERATE ----------------
"""@app.route('/auto_batches')
def auto_batches():
    if not session.get('admin'):
        return redirect('/login')

    month = datetime.now().strftime("%B")

    db.session.add_all([
        Batch(start_date=f"1 {month}", end_date=f"15 {month}"),
        Batch(start_date=f"16 {month}", end_date=f"30 {month}")
    ])
    db.session.commit()

    return redirect('/admin')
"""
# ---------------- EDIT BATCH ----------------
@app.route('/edit_batch/<int:id>/<start>/<end>/<int:cap>')
def edit_batch(id, start, end, cap):
    b = Batch.query.get(id)
    if b:
        b.start_date = start
        b.end_date = end
        b.capacity = cap
        db.session.commit()
    return "updated"

# ---------------- DELETE BATCH ----------------
@app.route('/delete_batch/<int:id>')
def delete_batch(id):
    b = Batch.query.get(id)
    if b:
        db.session.delete(b)
        db.session.commit()
    return "deleted"

###### ----- Gallery
@app.route('/gallery')
def gallery():

    hospital = Gallery.query.filter_by(category='hospital').all()
    doctors = Gallery.query.filter_by(category='doctors').all()
    interns = Gallery.query.filter_by(category='interns').all()
    events = Gallery.query.filter_by(category='events').all()
    panchakarma = Gallery.query.filter_by(category='panchakarma').all()

    return render_template(
        "gallery.html",
        hospital=hospital,
        doctors=doctors,
        interns=interns,
        events=events,
        panchakarma=panchakarma
    )

#---------------------------------------students Details CLickable by Admin-----------
@app.route('/student/<int:id>')
def student_detail(id):

    if not session.get('admin'):
        return redirect('/login')

    student = Student.query.get(id)

    batch = Batch.query.get(student.batch_id)

    return render_template('student_detail.html', student=student, batch=batch)


# ---------------- STUDENT CONTROL ----------------
@app.route('/mark_paid/<int:id>')
def mark_paid(id):

    s = db.session.get(Student, id)

    if s:

        s.payment_status = "Paid"
        db.session.commit()

        threading.Thread(
            target=send_email,
            args=(
                s.email,
                "Application Verified ✅",
                f"""
Dear {s.name},

Greetings from Amrutha Aarogya Kendra Ayurvedic Hospital.

We are pleased to inform you that your application and payment proof have been successfully verified.

Current Status:
--------------------------------------
Payment Status     : Verified ✅
Application Status : Accepted ✅
Internship Status  : Confirmed 🎉
--------------------------------------

You are eligible to attend the Training programme.

Please report to Amrutha Aarogya Kendra Ayurvedic Hospital as per your selected internship schedule and reporting time. 
We look forward to welcoming you.

Warm Regards,

Dr.Tukaram Umarani 
        (Ayurvedacharya)

Training & Internship Department
Amrutha Aarogya Kendra Ayurvedic Hospital Kalloli
"""
            )
        ).start()

    return "ok"

###-- MArk Completed
@app.route('/mark_completed/<int:id>')
def mark_completed(id):

    s = db.session.get(Student, id)

    if s:
        s.completion_status = "Completed"
        db.session.commit()

    return "ok"

#------------------delete student 
@app.route('/delete_student/<int:id>')
def delete_student(id):

    s = db.session.get(Student, id)

    if s:

        # Send rejection email
        threading.Thread(
            target=send_email,
            args=(
                s.email,
                "Internship Application Status",
                f"""
                Dear {s.name},

                Greetings from Amrutha Aarogya Kendra Ayurvedic Hospital.

                Thank you for your interest in our Internship Programme.

                After careful review of your application, we regret to inform you that your application has not been selected for the current internship batch.

                We sincerely appreciate the time and effort you invested in applying. Due to limited internship seats and the selection process, we are unable to offer you a position in this batch.

                We encourage you to apply again for our upcoming internship batches, and we would be pleased to consider your application in the future.

                We wish you every success in your academic and professional journey.

                Warm Regards,

                Dr. Tukaram Umarani
                (Ayurvedacharya)

                Training & Internship Department
                Amrutha Aarogya Kendra Ayurvedic Hospital, Kalloli
                """
            )
        ).start()

        batch = db.session.get(Batch, s.batch_id)

        if batch and batch.filled_slots > 0:
            batch.filled_slots -= 1

        db.session.delete(s)
        db.session.commit()

    return "deleted"

#--------------------------batches count fix
@app.route('/fix_batch_counts')
def fix_batch_counts():

    for batch in Batch.query.all():

        batch.filled_slots = Student.query.filter_by(
            batch_id=batch.id
        ).count()

    db.session.commit()

    return "Batch counts fixed ✅"

# ---------------- CSV UPLOAD ----------------
@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    file = request.files['file']

    reader = csv.reader(file.stream.read().decode("UTF-8").splitlines())
    next(reader)

    for r in reader:
        db.session.add(Student(
            name=r[0],
            email=r[1],
            phone=r[2],
            college=r[3],
            batch_id=int(r[4]),
            payment_status="Pending"
        ))

    db.session.commit()
    return redirect('/admin')

# ---------------- EXPORT EXCEL ----------------
from flask import send_file
import pandas as pd
import io   
from datetime import datetime

@app.route('/export_excel')
def export_excel():
    try:
        data = [{
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Name": s.name,
            "Email": s.email,
            "Phone": s.phone,
            "College": s.college,
            "Seat": s.seat,
            "Gender": s.gender,
            "Batch": s.batch_id,
            "Status": s.application_status
        } for s in Student.query.all()]

        if not data:
            return "No student data available"

        df = pd.DataFrame(data)

        output = io.BytesIO()
        df.to_excel(output, index=False, engine="openpyxl")  # ✅ IMPORTANT
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="students.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return str(e)   # ✅ show error for debugging

# ---------------- CERTIFICATE ----------------


@app.route('/certificate/<int:id>')
def certificate(id):
        s = db.session.get(Student, id)
        if s is None:
            return "Student not found", 404
        if s.application_status != "Approved":
            return "Certificate available only for approved trainees"

        if s.payment_status != "Paid":
            return "Payment not completed"

        if s.completion_status != "Completed":
            return "Training not completed"

        batch = db.session.get(Batch, s.batch_id) if s.batch_id else None

        start_fmt = end_fmt = None
        if batch and batch.start_date and batch.end_date:
            try:
                start_fmt = datetime.strptime(batch.start_date, "%Y-%m-%d").strftime("%d-%b-%Y")
                end_fmt = datetime.strptime(batch.end_date, "%Y-%m-%d").strftime("%d-%b-%Y")
            except ValueError:
                start_fmt = batch.start_date
                end_fmt = batch.end_date

        buffer = io.BytesIO()

        c = canvas.Canvas(
            buffer,
            pagesize=letter
        )
        
        width, height = letter
        
        draw_certificate(
            c,
            width,
            height,
            student_name=s.name,
            training_type=s.seat or "VIDDHA ANIKARMA & PANCHAKARMA",
            batch_start=start_fmt,
            batch_end=end_fmt,
            cert_no=f"AAK-{s.id:04d}",
            logo_path="static/logo.jpg"
        )
        
        c.showPage()
        c.save()
        
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
           
            download_name=f"Amruta Arogya Kendra Training Certificate - {s.name}.pdf",
            mimetype="application/pdf",
        )


# ---------------- RECEIPT ----------------
@app.route('/receipt/<int:id>')
def receipt(id):
    student = Student.query.get(id)
    return render_template("receipt.html", student=student)



visits = 0

@app.route('/')
def home():
    global visits
    visits += 1
    return render_template("index.html", visits=visits)

# ---------------- INIT ----------------
import calendar

# ✅ AUTO CREATE INITIAL BATCHES (RUN ONLY ONCE)
def create_initial_batches():

    year = datetime.now().year

    for month in range(1, 13):

        # ✅ FULL MONTH
        last_day = calendar.monthrange(year, month)[1]

        start1 = f"{year}-{month:02d}-01"
        end1 = f"{year}-{month:02d}-{last_day}"

        if not Batch.query.filter_by(start_date=start1).first():
            db.session.add(Batch(
                start_date=start1,
                end_date=end1,
                capacity=6,
                filled_slots=0
            ))

        # ✅ MID MONTH (15 → 14 next)
        if month == 12:
            next_month = 1
            next_year = year + 1
        else:
            next_month = month + 1
            next_year = year

        start2 = f"{year}-{month:02d}-15"
        end2 = f"{next_year}-{next_month:02d}-14"

        if not Batch.query.filter_by(start_date=start2).first():
            db.session.add(Batch(
                start_date=start2,
                end_date=end2,
                capacity=6,
                filled_slots=0
            ))

    db.session.commit()

# ✅ FIXED PREPARE FUNCTION (VERY IMPORTANT)
from datetime import datetime

def prepare_batches():

    batches = Batch.query.order_by(Batch.start_date).all()

    result = []

    today = datetime.today()

    current_month = datetime(
        today.year,
        today.month,
        1
    )

    if today.month == 12:
        next_month = datetime(today.year + 1, 1, 1)
        limit_month = datetime(today.year + 1, 2, 1)
    elif today.month == 11:
        next_month = datetime(today.year, 12, 1)
        limit_month = datetime(today.year + 1, 1, 1)
    else:
        next_month = datetime(today.year, today.month + 1, 1)
        limit_month = datetime(today.year, today.month + 2, 1)

    for b in batches:

        try:
            start = datetime.strptime(
                b.start_date,
                "%Y-%m-%d"
            )

            end = datetime.strptime(
                b.end_date,
                "%Y-%m-%d"
            )

        except:
            continue

        # admin blocked
        if hasattr(b, "is_active") and not b.is_active:
            continue

        # current month + next month only
        if start < current_month:
            continue

        if start >= limit_month:
            continue

        male_count = Student.query.filter_by(
            batch_id=b.id,
            gender="Male"
        ).count()

        female_count = Student.query.filter_by(
            batch_id=b.id,
            gender="Female"
        ).count()

        result.append({
            "id": b.id,
            "label": f"{start.strftime('%d %b')} → {end.strftime('%d %b')}",
            "male_left": max(0, 3 - male_count),
            "female_left": max(0, 3 - female_count)
        })

    return result

#---------------Toggle Block / Unblock batches manually by Admin
@app.route('/toggle_batch/<int:id>')
def toggle_batch(id):

    if not session.get('admin'):
        return redirect('/login')

    batch = Batch.query.get_or_404(id)

    batch.is_active = not batch.is_active

    db.session.commit()

    return redirect('/admin')



# ✅ ✅ MOVE DB INIT HERE (IMPORTANT)
with app.app_context():
    db.create_all()
    if not Batch.query.first():
        create_initial_batches()

    #create_initial_batches()
    
    

    
# ------------------Email auto meaasge------------------
#-@#$$________+--------------------------

import smtplib
from email.mime.text import MIMEText

import smtplib
from email.mime.text import MIMEText

def send_email(to_email, subject, message):
    try:
        import smtplib
        from email.mime.text import MIMEText

        sender = "amarsunadholi1415@gmail.com"       # ✅ your gmail
        password = "mgwetuaewypxhemm"        # ✅ app password (NOT normal password)

        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email

        # ✅ timeout added (important)
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()

        print("✅ Email sent successfully")

    except Exception as e:
        print("❌ Email failed:", e)


#-------------------- Certificate
import io
import math
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

NAVY = (0.086, 0.196, 0.337)
NAVY_DARK = (0.05, 0.13, 0.24)
GOLD = (0.75, 0.62, 0.22)
INK = (0.09, 0.13, 0.18)
CREAM = (0.996, 0.992, 0.973)


def _fit_font(c, text, font, max_w, start, min_size=13):
    size = start
    while size > min_size and c.stringWidth(text, font, size) > max_w:
        size -= 1
    return size


def _draw_spaced_centered(c, text, font, size, cx, y, tracking, color):
    c.setFont(font, size)
    widths = [c.stringWidth(ch, font, size) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    c.setFillColorRGB(*color)
    for ch, w in zip(text, widths):
        c.drawString(x, y, ch)
        x += w + tracking


def _draw_lotus_watermark(c, cx, cy, r, petals=16, color=GOLD, alpha=0.06):
    c.saveState()
    c.setFillAlpha(alpha)
    c.setFillColorRGB(*color)
    for i in range(petals):
        angle = (360 / petals) * i
        c.saveState()
        c.translate(cx, cy)
        c.rotate(angle)
        p = c.beginPath()
        p.moveTo(0, 0)
        p.curveTo(r * 0.28, r * 0.35, r * 0.22, r * 0.85, 0, r)
        p.curveTo(-r * 0.22, r * 0.85, -r * 0.28, r * 0.35, 0, 0)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.restoreState()
    c.setFillAlpha(alpha * 1.4)
    c.circle(cx, cy, r * 0.16, stroke=0, fill=1)
    c.restoreState()


def _draw_ribbon_flag(c, outer, bar_w, x0, y0, height_span, gold, navy, flip_y=False):
    """One navy/gold folded-ribbon flag. flip_y mirrors it vertically
    so the same shape can sit at a top or bottom corner."""
    c.saveState()
    p = c.beginPath()
    if not flip_y:
        p.moveTo(x0, y0)
        p.lineTo(x0 + bar_w, y0)
        p.lineTo(x0 + bar_w, y0 - height_span + 34)
        p.lineTo(x0, y0 - height_span)
    else:
        p.moveTo(x0, y0)
        p.lineTo(x0 + bar_w, y0)
        p.lineTo(x0 + bar_w, y0 + height_span - 34)
        p.lineTo(x0, y0 + height_span)
    p.close()
    c.setFillColorRGB(*navy)
    c.drawPath(p, stroke=0, fill=1)
    c.setStrokeColorRGB(*gold)
    c.setLineWidth(2)
    if not flip_y:
        c.line(x0 - 1, y0 - height_span + 16, x0 + bar_w + 1, y0 - height_span + 50)
    else:
        c.line(x0 - 1, y0 + height_span - 16, x0 + bar_w + 1, y0 + height_span - 50)
    c.restoreState()


import random


def _draw_paper_texture(c, x0, y0, x1, y1, seed=42, density=1400, color=INK, alpha=0.035):
    """Very light stipple grain to simulate a paper texture — cheap but
    effective without needing an external texture image."""
    rnd = random.Random(seed)
    c.saveState()
    c.setFillAlpha(alpha)
    c.setFillColorRGB(*color)
    for _ in range(density):
        x = rnd.uniform(x0, x1)
        y = rnd.uniform(y0, y1)
        r = rnd.uniform(0.2, 0.55)
        c.circle(x, y, r, stroke=0, fill=1)
    c.restoreState()


def _draw_beveled_frame(c, x, y, w, h, thickness, gold, navy):
    """An inset picture-frame bevel: a light 'catching the light' edge
    on the top-left and a darker shadow edge on the bottom-right, so
    the border reads as a carved groove rather than a flat line."""
    gold_light = tuple(min(1, v + 0.22) for v in gold)
    gold_dark = tuple(max(0, v - 0.28) for v in gold)

    c.saveState()
    # base frame band
    c.setFillColorRGB(*gold)
    c.rect(x, y, w, h, stroke=0, fill=1)
    # carve out the inner window (cream shows back through)
    c.setFillColorRGB(*CREAM)
    c.rect(x + thickness, y + thickness, w - 2 * thickness, h - 2 * thickness, stroke=0, fill=1)

    # highlight along the outer top+left edge of the band
    c.setStrokeColorRGB(*gold_light)
    c.setLineWidth(1.1)
    c.line(x, y + h, x + w, y + h)
    c.line(x, y, x, y + h)

    # shadow along the outer bottom+right edge of the band
    c.setStrokeColorRGB(*gold_dark)
    c.setLineWidth(1.1)
    c.line(x, y, x + w, y)
    c.line(x + w, y, x + w, y + h)

    # inner edge gets the opposite treatment (groove feels carved-in)
    ix, iy, iw, ih = x + thickness, y + thickness, w - 2 * thickness, h - 2 * thickness
    c.setStrokeColorRGB(*gold_dark)
    c.setLineWidth(0.9)
    c.line(ix, iy + ih, ix + iw, iy + ih)
    c.line(ix, iy, ix, iy + ih)
    c.setStrokeColorRGB(*gold_light)
    c.line(ix, iy, ix + iw, iy)
    c.line(ix + iw, iy, ix + iw, iy + ih)

    c.setStrokeColorRGB(*navy)
    c.setLineWidth(1.6)
    c.rect(x + thickness, y + thickness, w - 2 * thickness, h - 2 * thickness, stroke=1, fill=0)
    c.restoreState()


def _draw_embossed_text_centered(c, text, font, size, cx, y, color, tracking=0, depth=0.9):
    """Foil-stamp / engraved look: a darker offset duplicate underneath
    the main text creates a subtle raised (or pressed-in) edge."""
    dark = tuple(max(0, v - 0.35) for v in color)
    light = tuple(min(1, v + 0.35) for v in color)
    if tracking:
        _draw_spaced_centered(c, text, font, size, cx + depth, y - depth, tracking, dark)
        _draw_spaced_centered(c, text, font, size, cx - depth * 0.4, y + depth * 0.4, tracking, light)
        _draw_spaced_centered(c, text, font, size, cx, y, tracking, color)
    else:
        c.setFont(font, size)
        c.setFillColorRGB(*dark)
        c.drawCentredString(cx + depth, y - depth, text)
        c.setFillColorRGB(*light)
        c.drawCentredString(cx - depth * 0.4, y + depth * 0.4, text)
        c.setFillColorRGB(*color)
        c.drawCentredString(cx, y, text)


def _draw_card_shadow(c, x, y, w, h, blur_steps=10, max_offset=14, alpha=0.05):
    """A soft, faked drop shadow (concentric offset rounded rects at
    decreasing opacity) behind the certificate card, so it reads as a
    lifted, dimensional object rather than flat page art."""
    c.saveState()
    for i in range(blur_steps, 0, -1):
        off = (max_offset / blur_steps) * i
        c.setFillAlpha(alpha)
        c.setFillColorRGB(0, 0, 0)
        c.roundRect(x + off * 0.4, y - off * 0.5, w, h, 10, stroke=0, fill=1)
    c.restoreState()
    """One pair of laurel leaves branching from the stem, used to build
    a wreath around the medallion seal. A second, lighter color on the
    leaf tips gives a two-tone, slightly dimensional look."""
    c.saveState()
    c.translate(x, y)
    c.rotate(angle)
    for side in (1, -1):
        p = c.beginPath()
        p.moveTo(0, 0)
        p.curveTo(side * 3 * scale, 2 * scale, side * 5 * scale, 6 * scale, 0, 9 * scale)
        p.curveTo(side * -1 * scale, 6 * scale, side * -1.5 * scale, 2 * scale, 0, 0)
        p.close()
        c.setFillColorRGB(*color)
        c.drawPath(p, stroke=0, fill=1)

        if color2:
            p2 = c.beginPath()
            p2.moveTo(0, 5 * scale)
            p2.curveTo(side * 2 * scale, 6 * scale, side * 3 * scale, 7.5 * scale, 0, 9 * scale)
            p2.curveTo(side * -0.6 * scale, 7.5 * scale, side * -0.8 * scale, 6 * scale, 0, 5 * scale)
            p2.close()
            c.setFillColorRGB(*color2)
            c.drawPath(p2, stroke=0, fill=1)
    c.restoreState()


def _draw_medallion_seal(c, cx, cy, r, gold=GOLD, navy=NAVY, ink=NAVY_DARK):
    """A more advanced 'award medal' seal: drop shadow for lift, a
    laurel wreath in two tones of gold, a metallic-look ring with a
    glossy highlight, a small star, and ribbon tails — closer to a
    real diploma/medal than a flat stamp."""
    gold_light = tuple(min(1, v + 0.16) for v in gold)
    gold_dark = tuple(max(0, v - 0.22) for v in gold)

    c.saveState()

    # ---- drop shadow (soft lift off the page) ----
    c.setFillAlpha(0.18)
    c.setFillColorRGB(0, 0, 0)
    c.circle(cx + 2.5, cy - 3, r + 2, stroke=0, fill=1)
    c.setFillAlpha(1)

    # ---- ribbon tails ----
    tail_w = 13
    for dx, twist in ((-9, 6), (9, -6)):
        p = c.beginPath()
        p.moveTo(cx + dx - tail_w / 2, cy - r + 6)
        p.lineTo(cx + dx + tail_w / 2, cy - r + 6)
        p.lineTo(cx + dx + tail_w / 2 + twist, cy - r - 34)
        p.lineTo(cx + dx + twist, cy - r - 40)
        p.lineTo(cx + dx - tail_w / 2 + twist, cy - r - 34)
        p.close()
        c.setFillColorRGB(*navy)
        c.drawPath(p, stroke=0, fill=1)
        # thin gold edge on each tail for a stitched/embroidered look
        c.setStrokeColorRGB(*gold)
        c.setLineWidth(0.6)
        c.line(cx + dx - tail_w / 2, cy - r + 6, cx + dx + tail_w / 2 + twist, cy - r - 34)

    # ---- outer metallic rings ----
    c.setFillColorRGB(*navy)
    c.circle(cx, cy, r, stroke=0, fill=1)

    c.setStrokeColorRGB(*gold_dark)
    c.setLineWidth(2.2)
    c.circle(cx, cy, r - 2, stroke=1, fill=0)
    c.setStrokeColorRGB(*gold)
    c.setLineWidth(1.2)
    c.circle(cx, cy, r - 5, stroke=1, fill=0)
    c.setStrokeColorRGB(*gold_light)
    c.setLineWidth(0.6)
    c.circle(cx, cy, r - 8, stroke=1, fill=0)

    # ---- laurel wreath, two-tone leaves, left and right arcs ----
    leaf_r = r - 7
    for base_angle, direction in ((205, 1), (-25, -1)):
        for i in range(7):
            a = base_angle + direction * i * 10
            rad = math.radians(a)
            lx = cx + leaf_r * math.cos(rad)
            ly = cy + leaf_r * math.sin(rad)
            scale = 0.58 + 0.05 * math.sin(i)
            _draw_laurel_leaf_pair(c, lx, ly, scale, a + 90, gold_dark, gold_light)

    # ---- small five-point star above the initials ----
    star_r_out = 5.2
    star_r_in = 2.1
    star_cy = cy + 15
    pts = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        rr = star_r_out if i % 2 == 0 else star_r_in
        pts.append((cx + rr * math.cos(ang), star_cy + rr * math.sin(ang)))
    star_path = c.beginPath()
    star_path.moveTo(*pts[0])
    for pt in pts[1:]:
        star_path.lineTo(*pt)
    star_path.close()
    c.setFillColorRGB(*gold_light)
    c.drawPath(star_path, stroke=0, fill=1)

    # ---- glossy highlight (upper-left) to suggest curved metal ----
    c.saveState()
    c.setFillAlpha(0.16)
    c.setFillColorRGB(1, 1, 1)
    c.translate(cx, cy)
    c.rotate(35)
    c.ellipse(-r * 0.55, r * 0.05, r * 0.05, r * 0.62, stroke=0, fill=1)
    c.restoreState()

    # ---- center initials ----
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Times-Bold", 14)
    c.drawCentredString(cx, cy - 8, "AAK")
    c.setFont("Helvetica", 5.6)
    c.setFillColorRGB(*gold_light)
    c.drawCentredString(cx, cy - 18, "EST. KALLOLI")

    c.restoreState()


def draw_certificate(
    c, width, height, *,
    student_name,
    training_type,
    batch_start,
    batch_end,
    doctor_name="Dr. Tukaram B Umarani",
    doctor_cred="MS (Ayu)",
    hospital_line1="AMRUTA AAROGYA KENDRA,",
    hospital_line2="SPECIALITY AYURVEDA HOSPITAL, KALLOLI",
    address_lines=None,
    name_prefix="",
    cert_no=None,
    logo_path="static/logo.jpg",
):
    """Draw one certificate onto canvas `c`.

    student_name / training_type / batch_start / batch_end are meant to
    come from your database (e.g. student_name=s.name, training_type=
    s.seat, ...) — nothing here is hardcoded to a particular student.
    The __main__ block at the bottom of this file is only a local
    preview/test and is never executed by your Flask app.
    """
    if address_lines is None:
        address_lines = [
            "Amruta Aarogya Kendra",
            "Speciality Ayurveda Hospital",
            "Kalloli-591224, Tq: Mudalagi",
            "Dist: Belagavi • Mob: 9742151414",
        ]

    c.setFillColorRGB(*CREAM)
    c.rect(0, 0, width, height, stroke=0, fill=1)

    outer = 18
    inner = 27
    cx = width / 2

    _draw_lotus_watermark(c, cx, height * 0.46, 150, petals=16)

    # ---- Bottom navy wave + gold trace line ----
    wave_h = 42
    c.saveState()
    p = c.beginPath()
    p.moveTo(0, 0)
    p.lineTo(0, wave_h * 0.5)
    p.curveTo(width * 0.16, wave_h * 1.35, width * 0.34, wave_h * 1.35, width * 0.5, wave_h * 0.55)
    p.curveTo(width * 0.66, wave_h * -0.2, width * 0.84, wave_h * -0.2, width, wave_h * 0.55)
    p.lineTo(width, 0)
    p.close()
    c.setFillColorRGB(*NAVY)
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()

    c.saveState()
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(1.4)
    p2 = c.beginPath()
    p2.moveTo(0, wave_h * 0.5 + 7)
    p2.curveTo(width * 0.16, wave_h * 1.35 + 7, width * 0.34, wave_h * 1.35 + 7, width * 0.5, wave_h * 0.55 + 7)
    p2.curveTo(width * 0.66, wave_h * -0.2 + 7, width * 0.84, wave_h * -0.2 + 7, width, wave_h * 0.55 + 7)
    c.drawPath(p2, stroke=1, fill=0)
    c.restoreState()

    # ---- Double border ----
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(1.2)
    c.rect(outer, outer, width - 2 * outer, height - 2 * outer, stroke=1, fill=0)

    c.setStrokeColorRGB(*NAVY)
    c.setLineWidth(1.8)
    c.rect(inner, inner, width - 2 * inner, height - 2 * inner, stroke=1, fill=0)

    # ---- Ribbon-flag corners — now symmetric on both edges ----
    bar_w = 20
    _draw_ribbon_flag(c, outer, bar_w, outer, height - outer, 148, GOLD, NAVY)                      # top-left
    _draw_ribbon_flag(c, outer, bar_w, outer, outer + wave_h * 0.5, 128, GOLD, NAVY, flip_y=True)    # bottom-left
    _draw_ribbon_flag(c, outer, bar_w, width - outer - bar_w, height - outer, 148, GOLD, NAVY)       # top-right
    _draw_ribbon_flag(c, outer, bar_w, width - outer - bar_w, outer + wave_h * 0.5, 128, GOLD, NAVY, flip_y=True)  # bottom-right

    # ---- Circular seal / logo ----
    seal_r = 46
    seal_cy = height - 100
    if logo_path:
        try:
            img = ImageReader(logo_path)
            c.drawImage(img, cx - seal_r, seal_cy - seal_r, width=seal_r * 2, height=seal_r * 2,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    # ---- Hospital name ----
    c.setFillColorRGB(*GOLD)
    c.setFont("Times-Bold", 17)
    c.drawCentredString(cx, height - 170, hospital_line1)
    c.setFont("Times-Bold", 11.5)
    c.drawCentredString(cx, height - 187, hospital_line2)

    # ---- CERTIFICATE ----
    _draw_spaced_centered(c, "CERTIFICATE", "Times-Bold", 42, cx, height - 246, 4.5, NAVY)

    c.saveState()
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(1)
    fl_y = height - 262
    c.line(cx - 130, fl_y, cx - 14, fl_y)
    c.line(cx + 14, fl_y, cx + 130, fl_y)
    c.setFillColorRGB(*GOLD)
    d = 3.2
    p5 = c.beginPath()
    p5.moveTo(cx - d, fl_y)
    p5.lineTo(cx, fl_y + d)
    p5.lineTo(cx + d, fl_y)
    p5.lineTo(cx, fl_y - d)
    p5.close()
    c.drawPath(p5, stroke=0, fill=1)
    c.restoreState()

    # ---- Subtitle ----
    _draw_spaced_centered(c, f"OF {training_type.upper()}", "Times-Bold", 12, cx, height - 282, 2.4, GOLD)

    # ---- "This is to certify that" ----
    c.setFillColorRGB(*INK)
    c.setFont("Times-Italic", 15)
    c.drawCentredString(cx, height - 316, "This is to certify that")

    # ---- Student name (always the caller's student_name — never hardcoded) ----
    name_text = f"{name_prefix} {student_name}".strip()
    name_font = "Times-Bold"
    name_size = _fit_font(c, name_text, name_font, width - 2 * inner - 100, 30)
    c.setFillColorRGB(*NAVY_DARK)
    c.setFont(name_font, name_size)
    c.drawCentredString(cx, height - 352, name_text)

    nw = c.stringWidth(name_text, name_font, name_size)
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(1)
    c.line(cx - nw / 2 - 26, height - 363, cx + nw / 2 + 26, height - 363)

    # ---- Body copy ----
    body_lines = [
        "has undergone and successfully completed a hands-on training",
        f"in {training_type} under the",
        f"expert guidance of {doctor_name}. {doctor_cred}, at",
        f"{hospital_line1.rstrip(',').title()}, {hospital_line2.title()}",
        f"during the period of From {batch_start} to {batch_end}.",
        "provided in depth exposure to classical Ayurveda procedures",
        "and Patient care, enhancing one's own Practical knowledge and",
        "Clinical skills.",
    ]
    c.setFillColorRGB(*INK)
    c.setFont("Times-Roman", 12)
    y = height - 390
    for line in body_lines:
        c.drawCentredString(cx, y, line)
        y -= 18.5

    div_y = y - 22
    c.saveState()
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(0.8)
    c.line(cx - 150, div_y, cx - 16, div_y)
    c.line(cx + 16, div_y, cx + 150, div_y)
    c.setFillColorRGB(*GOLD)
    c.circle(cx, div_y, 3, stroke=0, fill=1)
    c.circle(cx - 9, div_y, 1.6, stroke=0, fill=1)
    c.circle(cx + 9, div_y, 1.6, stroke=0, fill=1)
    c.restoreState()

    # ---- Footer: medallion seal (left) + signature (right) ----
    fy = 172

    _draw_medallion_seal(c, inner + 82, fy - 6, 40)

    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.7)
    c.line(width - 220, fy, width - 50, fy)

    c.setFillColorRGB(*NAVY_DARK)
    c.setFont("Times-Bold", 10.5)
    c.drawCentredString(width - 135, fy - 15, doctor_name)
    c.setFont("Times-Italic", 8.5)
    c.drawCentredString(width - 135, fy - 27, doctor_cred)
    c.setFont("Helvetica", 8)
    for i, line in enumerate(address_lines):
        c.drawCentredString(width - 135, fy - 40 - i * 11, line)

    if cert_no:
        c.setFillColorRGB(*NAVY_DARK)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(inner + 14, 78, f"Cert. No: {cert_no}")

    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(0.7)
    c.line(inner + 20, 68, width - inner - 20, 68)
    c.setFillColorRGB(*NAVY_DARK)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawCentredString(cx, 56,
                        "This certificate is system-generated by Amrutha Aarogya Kendra Ayurvedic Hospital.")


# ---------------------------------------------------------------------
# Flask route — drop-in replacement for the original /certificate/<id>
# ---------------------------------------------------------------------



import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
