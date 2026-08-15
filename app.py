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
from werkzeug.utils import secure_filename


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

if not os.path.exists("static/uploads/photos"):
    os.makedirs("static/uploads/photos")


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

print("SQLAlchemy =", SQLAlchemy)
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
    #photo = db.Column(db.String(255))

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
    photo = db.Column(db.String(255))
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
        photo_file = request.files.get("student_photo")
        if photo_file:

            if photo_file.content_length and (photo_file.content_length >5 * 1024 * 1024):
                return "Photo size exceeds 5 MB"

        seat = data.get('selected_seat')
        if not seat:
            return "Please select a seat"
        gender = data.get('gender')
        #dob = data.get("dob")

        filename = None
        photo_filename = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(f"static/uploads/{filename}")

        if photo_file and photo_file.filename:

            photo_filename = (f"photo_{int(datetime.now().timestamp())}_" 
                              f"{secure_filename(photo_file.filename)}")
            photo_file.save(f"static/uploads/photos/{photo_filename}")

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
        existing_seat = Student.query.filter_by(
        batch_id=batch.id,
        seat=seat
            ).first()
    
        if existing_seat:
            return f"Seat {seat} already booked"

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
            #selected_seat = request.form.get("selected_seat"),
            transaction_id=data.get('transaction_id'),
            payment_proof=filename,
            photo=photo_filename,
            payment_status="Pending"
        )

        batch.filled_slots += 1

        db.session.add(student)
        db.session.commit()
        session["student_id"] = student.id
        print("Saved Student ID:", student.id)

        
        

        # Email
        application_id = f"AAK-{student.id:05d}"

        photo_url = f"https://amrutaarogyakendraayurvedaspecialityhospitalkalloli.up.railway.app/static/uploads/photos/{student.photo}"

        email_message = f"""
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f8f4;padding:20px;">

        <div style="max-width:700px;margin:auto;background:white;padding:30px;border-radius:15px;border:1px solid #ddd;">

        <h2 style="text-align:center;color:#0f3a29;">
        🌿 Amrutha Aarogya Kendra
        </h2>

        <h3 style="text-align:center;color:#cf9f45;">
        Internship Application Received
        </h3>

        <p>
        Dear <b>{student.name}</b>,
        </p>

        <p>
        Thank you for applying for our Internship Program.
        Your application has been successfully received.
        </p>

        <div style="background:#e6f7ec;padding:15px;border-radius:10px;text-align:center;">
        <h3>Application ID</h3>
        <h2 style="color:#0f3a29;">{application_id}</h2>
        </div>

        <br>

        <div style="text-align:center;">
            <img
                src="{photo_url}"
                alt="Student Photo"
                width="120"
                height="140"
                style="
                    width:120px;
                    height:140px;
                    border-radius:10px;
                    border:3px solid #cf9f45;
                    object-fit:cover;
                "
            >
        </div>

        <br>

        <table width="100%" cellpadding="8" style="border-collapse:collapse;">

        <tr><td><b>Applicant Name</b></td><td>{student.name}</td></tr>
        <tr><td><b>Email Address</b></td><td>{student.email}</td></tr>
        <tr><td><b>Mobile Number</b></td><td>{student.phone}</td></tr>
        <tr><td><b>Age</b></td><td>{student.age}</td></tr>
        <tr><td><b>Gender</b></td><td>{student.gender}</td></tr>
        <tr><td><b>College</b></td><td>{student.college}</td></tr>
        <tr><td><b>Place</b></td><td>{student.place}</td></tr>
        <tr><td><b>District</b></td><td>{student.district}</td></tr>
        <tr><td><b>State</b></td><td>{student.state}</td></tr>
        <tr><td><b>Pincode</b></td><td>{student.pincode}</td></tr>
        <tr><td><b>Selected Seat</b></td><td>{student.seat}</td></tr>
        <tr><td><b>Transaction ID</b></td><td>{student.transaction_id}</td></tr>
        <tr><td><b>Payment Status</b></td><td>{student.payment_status or 'Pending'}</td></tr>
        <tr><td><b>Application Status</b></td><td>Under Review</td></tr>

        </table>

        <hr>

        <p>
        Your application has been forwarded to our Internship Committee for verification.
        </p>

        <p>
        Once the verification process is completed, you will receive another email regarding your admission status.
        </p>

        <p>
        Please save your Application ID for future reference.
        </p>

        <hr>

        <p>
        <b>Need Help?</b><br>
        📞 +91 97421 51414<br>
        📱 WhatsApp: +91 99168 03734
        </p>

        <p>
        Warm Regards,<br>
        <b>Dr. Tukaram Umarani</b><br>
        Ayurvedacharya<br>
        Amrutha Aarogya Kendra Ayurvedic Hospital
        </p>

        </div>

        </body>
        </html>
        """


        threading.Thread(
        target=send_email,
        args=(
            student.email,
            "Training Application Received ✅",
            email_message
        )
    ).start()
        
        return redirect(f'/success/{student.id}')

    except Exception as e:
        db.session.rollback()
        print("REGISTER ERROR:", str(e))
        return f"ERROR: {str(e)}"


#####----seat batch
@app.route("/debug_batch/<int:batch_id>")
def debug_batch(batch_id):

    students = Student.query.filter_by(
        batch_id=batch_id
    ).all()

    return jsonify([
        {
            "id": s.id,
            "name": s.name,
            "gender": s.gender,
            "seat": s.seat
        }
        for s in students
    ])

@app.route("/api/batches/<int:batch_id>/seats")
def get_batch_seats(batch_id):

    batch = Batch.query.get_or_404(batch_id)

    seats = {
        "M1": {"gender": "Male", "booked": False},
        "M2": {"gender": "Male", "booked": False},
        "M3": {"gender": "Male", "booked": False},

        "F1": {"gender": "Female", "booked": False},
        "F2": {"gender": "Female", "booked": False},
        "F3": {"gender": "Female", "booked": False},
    }

    booked_students = Student.query.filter_by(
        batch_id=batch_id
    ).all()

    for student in booked_students:

        if student.seat in seats:
            seats[student.seat]["booked"] = True

    male_available = sum(
        1 for seat in seats.values()
        if seat["gender"] == "Male" and not seat["booked"]
    )

    female_available = sum(
        1 for seat in seats.values()
        if seat["gender"] == "Female" and not seat["booked"]
    )

    return jsonify({
        "batch_id": batch_id,
        "seats": seats,
        "male_available": male_available,
        "female_available": female_available
    })


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
@app.route("/success/<int:student_id>")
def success(student_id):

    student = Student.query.get_or_404(student_id)

    application_id = f"AAK-{student.id:05d}"

    return render_template(
        "success.html",
        student=student,
        application_id=application_id
    )

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
    for b in all_batches:
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

        filename = secure_filename(file.filename)
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
            trainee_photo=s.photo,
            training_type="Ayurvedic Internship Training",
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

        import os

        sender = os.getenv("MAIL_USERNAME")
        password = os.getenv("MAIL_PASSWORD")        # ✅ app password (NOT normal password)

        msg = MIMEText(message, "html")
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
Certificate generator matching the "AMRUTA AAROGYA KENDRA" printed
template (navy + gold, ribboned left edge, wave footer, circular seal).

Drop-in replacement for the draw_certificate() function currently in
app.py. See the bottom of this file for the updated /certificate/<id>
route that calls it.
"""

import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# ---- Palette, matched from the template photo ----
NAVY = (0.086, 0.196, 0.337)       # deep navy blue
NAVY_DARK = (0.05, 0.13, 0.24)     # near-black navy for body text/signature
GOLD = (0.75, 0.62, 0.22)          # muted gold
INK = (0.09, 0.13, 0.18)
CREAM = (0.996, 0.992, 0.973)      # warm off-white page background


def _fit_font(c, text, font, max_w, start, min_size=13):
    """Shrink font size until `text` fits inside `max_w`."""
    size = start
    while size > min_size and c.stringWidth(text, font, size) > max_w:
        size -= 1
    return size


def _draw_spaced_centered(c, text, font, size, cx, y, tracking, color):
    """Draw letter-spaced (tracked) centered text — used for the big
    'CERTIFICATE' title and the gold subtitle, to match the template's
    wide, tracked display lettering."""
    c.setFont(font, size)
    widths = [c.stringWidth(ch, font, size) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    c.setFillColorRGB(*color)
    for ch, w in zip(text, widths):
        c.drawString(x, y, ch)
        x += w + tracking


def draw_certificate(
    c, width, height, *,
    student_name,
    trainee_photo=None,
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
    """Draw the certificate onto an already-created canvas `c`.

    Only student_name, training_type, batch_start and batch_end are
    required — everything else has sane defaults matching the template
    and can be overridden per call if needed.
    """
    if address_lines is None:
        address_lines = [
            "Amruta Aarogya Kendra,",
            "Speciality Ayurveda Hospital",
            "Kalloli-591224 Tq: Mudalagi",
            "Dist: Belagavi Mob: 9742151414",
        ]

    # ---- Page background ----
    c.setFillColorRGB(*CREAM)
    c.rect(0, 0, width, height, stroke=0, fill=1)

    outer = 18
    inner = 27

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

    # ---- Left-edge ribbon flags (top + bottom) ----
    bar_w = 20

    c.saveState()
    top_bar_h = 148
    p3 = c.beginPath()
    p3.moveTo(outer, height - outer)
    p3.lineTo(outer + bar_w, height - outer)
    p3.lineTo(outer + bar_w, height - outer - top_bar_h + 34)
    p3.lineTo(outer, height - outer - top_bar_h)
    p3.close()
    c.setFillColorRGB(*NAVY)
    c.drawPath(p3, stroke=0, fill=1)
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(2)
    c.line(outer - 1, height - outer - top_bar_h + 16, outer + bar_w + 1, height - outer - top_bar_h + 50)
    c.restoreState()

    c.saveState()
    bot_bar_h = 128
    base_y = outer + wave_h * 0.5
    p4 = c.beginPath()
    p4.moveTo(outer, base_y)
    p4.lineTo(outer + bar_w, base_y)
    p4.lineTo(outer + bar_w, base_y + bot_bar_h - 30)
    p4.lineTo(outer, base_y + bot_bar_h)
    p4.close()
    c.setFillColorRGB(*NAVY)
    c.drawPath(p4, stroke=0, fill=1)
    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(2)
    c.line(outer - 1, base_y + bot_bar_h - 46, outer + bar_w + 1, base_y + bot_bar_h - 10)
    c.restoreState()

    cx = width / 2

    # ---- Circular seal / logo ----
    seal_r = 46
    seal_cy = height - 100
    if logo_path:
        try:
            img = ImageReader(logo_path)
            c.drawImage(img, cx - seal_r, seal_cy - seal_r, width=seal_r * 2, height=seal_r * 2,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            pass  # no logo on disk — certificate still renders correctly without it

    # ---- Hospital name ----
    c.setFillColorRGB(*GOLD)
    c.setFont("Times-Bold", 17)
    c.drawCentredString(cx, height - 170, hospital_line1)
    c.setFont("Times-Bold", 11.5)
    c.drawCentredString(cx, height - 187, hospital_line2)

    # ---- CERTIFICATE ----
    _draw_spaced_centered(c, "CERTIFICATE", "Times-Bold", 42, cx, height - 246, 4.5, NAVY)

    # ---- Subtitle ----
    _draw_spaced_centered(c, f"OF {training_type.upper()}", "Helvetica-Bold", 11.5, cx, height - 272, 2.2, GOLD)

    # ---- "This is to certify that" ----
    c.setFillColorRGB(*INK)
    c.setFont("Times-Italic", 15)
    c.drawCentredString(cx, height - 306, "This is to certify that")

    # ---- Student name ----
    name_text = f"{name_prefix} {student_name}".strip()
    name_font = "Times-Bold"
    name_size = _fit_font(c, name_text, name_font, width - 2 * inner - 100, 24)
    c.setFillColorRGB(*NAVY_DARK)
    c.setFont(name_font, name_size)
    c.drawCentredString(cx, height - 340, name_text)

    nw = c.stringWidth(name_text, name_font, name_size)
    c.setStrokeColorRGB(*NAVY)
    c.setLineWidth(0.8)
    c.line(cx - nw / 2 - 24, height - 350, cx + nw / 2 + 24, height - 350)

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
    c.setFont("Helvetica", 11.5)
    y = height - 375
    for line in body_lines:
        c.drawCentredString(cx, y, line)
        y -= 17.5

    # ---- Footer: address block (bottom-left) ----
    fy = 150
    c.setFillColorRGB(*NAVY_DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(inner + 22, fy + 46, doctor_name)
    c.setFont("Helvetica", 8.5)
    c.drawString(inner + 22, fy + 34, doctor_cred)
    c.setFont("Helvetica-Bold", 9)
    for i, line in enumerate(address_lines):
        c.drawString(inner + 22, fy + 20 - i * 11, line)

    # ---- Footer: signature (bottom-right) ----
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.7)
    c.line(width - inner - 170, fy - 4, width - inner - 22, fy - 4)
    c.setFillColorRGB(*NAVY_DARK)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width - inner - 96, fy - 16, f"{doctor_name}. {doctor_cred}")

    #------ photo-------------------------
    # ---- Trainee Photo ----

    photo_x = inner + 15
    photo_y = fy - 70

    if trainee_photo:

        try:
            trainee_img = ImageReader(f"static/uploads/photos/{trainee_photo}")
            c.drawImage(trainee_img,photo_x,photo_y,width=90,height=110,preserveAspectRatio=True,mask='auto')

        except Exception as e:
            print("Photo Error:", e)

    # ---- Hospital Seal ----

    try:
        seal = ImageReader("static/seal.png")
        c.drawImage(seal,photo_x + 55,photo_y - 10,width=65,height=65,mask='auto')

    except Exception as e:
        print("Seal Error:", e)

    # ---- Optional unobtrusive certificate number (not in the original
    # template, but useful for your own records — small, muted, corner) ----
    if cert_no:
        c.setFillColorRGB(0.55, 0.55, 0.55)
        c.setFont("Helvetica", 7)
        c.drawString(inner + 6, inner + 6, cert_no)

        # Thin closing rule + tagline
        c.setStrokeColorRGB(*GOLD)
        c.setLineWidth(0.6)
        c.line(inner + 20, inner + 14, width - inner - 20, inner + 14)
        c.setFillColorRGB(*NAVY_DARK)
        c.setFont("Helvetica-Oblique", 8)
        c.drawCentredString(cx, inner + 4,
                            "This certificate is system-generated by Amrutha Aarogya Kendra Ayurvedic Hospital.")


# ---------------------------------------------------------------------
# Flask route — drop-in replacement for the original /certificate/<id>
# ---------------------------------------------------------------------




import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
