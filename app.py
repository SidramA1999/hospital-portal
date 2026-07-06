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

# Cache static files for 1 year
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000


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
                "Training Application Received ✅",

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
import os
from openai import OpenAI

key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=key) if key else None


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
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        draw_certificate(
            c, width, height,
            student_name=s.name,
            batch_start=start_fmt,
            batch_end=end_fmt,
            cert_no=f"AAK-{s.id:04d}",
            issue_date=datetime.now().strftime("%d-%b-%Y"),
            logo_path="static/logo.jpg",
            seal_path="static/seal.png",
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
    today = datetime.today().date()

    for b in batches:
        try:
            start = datetime.strptime(b.start_date, "%Y-%m-%d")
            end = datetime.strptime(b.end_date, "%Y-%m-%d")
        except:
            continue

        
# ✅ ✅ SKIP PAST BATCHES
        if end.date() < today:
            continue


        male_count = Student.query.filter_by(batch_id=b.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=b.id, gender="Female").count()

        male_left = max(0, 3 - male_count)
        female_left = max(0, 3 - female_count)

        # ✅ ✅ FIXED LABEL (THIS WAS YOUR MAIN BUG)
       
        #label = f"{start.strftime('%B %Y')} ({start.day} – {end.day}) (👨 {male_left} | 👩 {female_left} left)"
        label = f"{start.strftime('%d %b')} → {end.strftime('%d %b')} (👨 {male_left} | 👩 {female_left})"

        result.append({
            "id": b.id,
            "label": label,
            "male_left": male_left,
            "female_left": female_left
        })

    return result




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
"""
Certificate generator for Amrutha Aarogya Kendra.

Drop this into your Flask app. It fixes the bug in the original route
(`end = ...` ran outside the `if batch:` guard, so a student with no
batch would crash with AttributeError on `batch.end_date`), and upgrades
the certificate's visual design.

Design notes
------------
- Uses reportlab's roundRect for a soft double border instead of two
  hard-cornered rects.
- Draws a vector emblem (concentric circles + initials) as a fallback
  seal/logo, so the certificate still looks complete if
  static/logo.jpg or static/seal.png are missing -- it tries the real
  images first via PIL/ImageReader and only falls back if that fails.
- Long student names are auto-shrunk to fit on one line instead of
  overflowing the page width.
- Renders to an in-memory BytesIO buffer instead of writing a file to
  disk, so concurrent requests can never collide on the same filename
  and nothing needs to be cleaned up afterwards.
"""

import io
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# ---- Brand palette (matches the dashboard) ----------------------------
PRIMARY = (15 / 255, 58 / 255, 41 / 255)      # #0f3a29 deep green
SECONDARY = (45 / 255, 106 / 255, 79 / 255)   # #2d6a4f green
ACCENT = (207 / 255, 159 / 255, 69 / 255)     # #cf9f45 gold
INK = (18 / 255, 39 / 255, 30 / 255)          # #12271e near-black green
INK_SOFT = (81 / 255, 101 / 255, 87 / 255)    # #516557 muted green-grey


def _fit_font_size(c, text, font_name, max_width, start_size, min_size=14):
    """Shrink font size until `text` fits inside `max_width`."""
    size = start_size
    while size > min_size and c.stringWidth(text, font_name, size) > max_width:
        size -= 1
    return size


def _draw_emblem(c, cx, cy, radius, logo_path=None):
    """Draw the hospital emblem. Tries a real logo image first, falls
    back to a drawn vector emblem so the certificate never looks broken."""
    if logo_path:
        try:
            img = ImageReader(logo_path)
            size = radius * 2
            c.drawImage(img, cx - radius, cy - radius, width=size, height=size,
                        preserveAspectRatio=True, mask='auto')
            return
        except Exception:
            pass  # fall through to vector emblem

    c.saveState()
    c.setFillColorRGB(*ACCENT)
    c.circle(cx, cy, radius, stroke=0, fill=1)
    c.setFillColorRGB(*PRIMARY)
    c.circle(cx, cy, radius - 6, stroke=0, fill=1)
    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(1.2)
    c.circle(cx, cy, radius - 12, stroke=1, fill=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", radius * 0.55)
    c.drawCentredString(cx, cy - radius * 0.2, "AAK")
    c.restoreState()


def _draw_seal(c, cx, cy, radius, seal_path=None):
    if seal_path:
        try:
            img = ImageReader(seal_path)
            size = radius * 2
            c.drawImage(img, cx - radius, cy - radius, width=size, height=size,
                        preserveAspectRatio=True, mask='auto')
            return
        except Exception:
            pass

    c.saveState()
    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(2)
    c.circle(cx, cy, radius, stroke=1, fill=0)
    c.setLineWidth(0.75)
    c.circle(cx, cy, radius - 6, stroke=1, fill=0)
    c.setFillColorRGB(*SECONDARY)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(cx, cy + 4, "OFFICIAL")
    c.drawCentredString(cx, cy - 8, "SEAL")
    c.restoreState()


def draw_certificate(c, width, height, *, student_name, batch_start,
                      batch_end, cert_no, issue_date,
                      logo_path="static/logo.jpg", seal_path="static/seal.png"):
    """Draw the full certificate onto an already-created canvas `c`."""

    margin_outer = 24
    margin_inner = 34

    # ---- Border --------------------------------------------------------
    c.setStrokeColorRGB(*PRIMARY)
    c.setLineWidth(2.2)
    c.roundRect(margin_outer, margin_outer, width - 2 * margin_outer,
                height - 2 * margin_outer, 14, stroke=1, fill=0)

    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(1)
    c.roundRect(margin_inner, margin_inner, width - 2 * margin_inner,
                height - 2 * margin_inner, 10, stroke=1, fill=0)

    cx = width / 2

    # ---- Emblem ----------------------------------------------------------
    _draw_emblem(c, cx, height - 118, 46, logo_path)

    # ---- Header ------------------------------------------------------
    c.setFillColorRGB(*PRIMARY)
    c.setFont("Helvetica-Bold", 21)
    c.drawCentredString(cx, height - 190, "A M R U T H A   A A R O G Y A   K E N D R A")

    c.setFillColorRGB(*SECONDARY)
    c.setFont("Helvetica", 12.5)
    c.drawCentredString(cx, height - 210, "SPECIALITY AYURVEDIC HOSPITAL, KALLOLI")

    # ---- Title with ornamental rule -----------------------------------
    c.setFillColorRGB(*ACCENT)
    c.setFont("Times-Bold", 30)
    c.drawCentredString(cx, height - 258, "Trainee Certificate")

    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(1.4)
    c.line(cx - 150, height - 270, cx - 12, height - 270)
    c.line(cx + 12, height - 270, cx + 150, height - 270)
    c.setFillColorRGB(*ACCENT)
    c.circle(cx, height - 270, 4, stroke=0, fill=1)

    # ---- "This is to certify that" -------------------------------------
    c.setFillColorRGB(*INK_SOFT)
    c.setFont("Helvetica-Oblique", 13)
    c.drawCentredString(cx, height - 305, "This is to certify that")

    # ---- Student name (auto-shrinks to fit) -----------------------------
    name_text = student_name.upper()
    name_font = "Times-Bold"
    name_size = _fit_font_size(c, name_text, name_font, width - 2 * margin_inner - 60, 26)
    c.setFillColorRGB(*PRIMARY)
    c.setFont(name_font, name_size)
    c.drawCentredString(cx, height - 345, name_text)

    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(0.8)
    name_width = c.stringWidth(name_text, name_font, name_size)
    c.line(cx - name_width / 2 - 20, height - 356, cx + name_width / 2 + 20, height - 356)

    # ---- Body copy -------------------------------------------------------
    body_lines = [
        "has successfully completed the internship programme at",
        "Amrutha Aarogya Kendra Ayurvedic Hospital, demonstrating dedication,",
        "professionalism and commitment throughout the training period.",
    ]
    c.setFillColorRGB(*INK)
    c.setFont("Helvetica", 12.5)
    y = height - 390
    for line in body_lines:
        c.drawCentredString(cx, y, line)
        y -= 19

    # ---- Training period --------------------------------------------
    if batch_start and batch_end:
        period_text = f"Training Period:  {batch_start}  to  {batch_end}"
    else:
        period_text = "Training Period:  N/A"
    c.setFillColorRGB(*SECONDARY)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(cx, y - 20, period_text)

    # ---- Footer block: certificate no / issue date / signatures / seal --
    footer_y = 150
    c.setFillColorRGB(*INK_SOFT)
    c.setFont("Helvetica", 10.5)
    c.drawString(margin_inner + 20, footer_y + 34, f"Certificate No:  {cert_no}")
    c.drawString(margin_inner + 20, footer_y + 18, f"Issue Date:  {issue_date}")

    # Signature lines
    c.setStrokeColorRGB(*INK_SOFT)
    c.setLineWidth(0.8)
    c.line(margin_inner + 20, footer_y - 30, margin_inner + 160, footer_y - 30)
    c.line(width - margin_inner - 160, footer_y - 30, width - margin_inner - 20, footer_y - 30)

    c.setFillColorRGB(*INK)
    c.setFont("Helvetica", 10.5)
    c.drawCentredString(margin_inner + 90, footer_y - 44, "Medical Director")
    c.drawCentredString(width - margin_inner - 90, footer_y - 44, "Chief Physician")

    # Seal, centered under the title area at the bottom
    _draw_seal(c, cx, footer_y - 10, 34, seal_path)

    # Thin closing rule + tagline
    c.setStrokeColorRGB(*ACCENT)
    c.setLineWidth(0.6)
    c.line(margin_inner + 20, margin_inner + 14, width - margin_inner - 20, margin_inner + 14)
    c.setFillColorRGB(*INK_SOFT)
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(cx, margin_inner + 4,
                         "This certificate is system-generated by Amrutha Aarogya Kendra Ayurvedic Hospital.")


# ---------------------------------------------------------------------
# Flask route — drop-in replacement for the original /certificate/<id>
# ---------------------------------------------------------------------



import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
