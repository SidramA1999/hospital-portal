from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash
import razorpay
import csv
import pandas as pd
from reportlab.pdfgen import canvas
from datetime import datetime



app = Flask(__name__)
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
import threading

@app.route("/update_status/<int:id>/<status>")
def update_status(id, status):

    student = Student.query.get(id)

    if not student:
        return "Student not found ❌"

    # ✅ APPROVE
    if status == "approve":
        student.application_status = "Approved"

        threading.Thread(
            target=send_email,
            args=(
                student.email,
                "Application Approved ✅",
                "Congratulations! You are eligible for training 🎉"
            )
        ).start()

    # ✅ REJECT
    elif status == "reject":
        student.application_status = "Rejected"

        threading.Thread(
            target=send_email,
            args=(
                student.email,
                "Application Status ❌",
                "We regret to inform you that you are not eligible for training."
            )
        ).start()

    else:
        return "Invalid action ❌"

    db.session.commit()

    return redirect("/admin")


# ---------------- REGISTER ----------------


from datetime import datetime
"""
@app.route('/register', methods=['GET','POST'])
def register():

    # ✅ GET request
    if request.method == 'GET':
        return render_template("register.html", batches=prepare_batches())

    # ✅ POST request
    data = request.form
    file = request.files.get('payment_proof')

    
    seat = data.get('seat')   
    print("Selected seat:", seat)


    # ✅ handle upload
    filename = None
    if file:
        filename = file.filename
        file.save(f"static/uploads/{filename}")

    # ✅ get batch
    batch_id = int(data.get('batch_id'))
    gender = data.get('gender')

    batch = db.session.get(Batch, batch_id)

    if not batch:
        return "Invalid batch"

    # ✅ capacity check
    if batch.filled_slots >= batch.capacity:
        return "Batch is full"

    # ✅ gender seat check
    male_count = Student.query.filter_by(batch_id=batch.id, gender="Male").count()
    female_count = Student.query.filter_by(batch_id=batch.id, gender="Female").count()

    if gender == "Male" and male_count >= 3:
        return "No seats for Male"

    if gender == "Female" and female_count >= 3:
        return "No seats for Female"

    # ✅ save student
    student = Student(
        name=data.get('name'),
        email=data.get('email'),
        phone=data.get('phone'),
        #age=data.get('age'),
        age = int(data.get('age').replace(" Yrs", "").strip()),
        college=data.get('college'),
        pincode=data.get('pincode'),
        state=data.get('state'),
        district=data.get('district'),
        place=data.get('place'),
        batch_id=batch.id,
        seat=seat,
        gender=gender,
        transaction_id=data.get('transaction_id'),  # ✅ IMPORTANT
        payment_proof=filename,                    # ✅ IMPORTANT
        payment_status="Pending"
    )

    batch.filled_slots += 1

    db.session.add(student)
    db.session.commit()
    
    # ✅ SEND EMAIL AFTER REGISTRATION (INSIDE FUNCTION ✅)
    threading.Thread(
        target=send_email,
        args=(
            data.get('email'),
            "Registration Successful ✅",
            "Your application has been submitted successfully. You can check your status on the website."
        )
    ).start()
    try:
    # your register code here
        except Exception as e:
    return str(e)

    return redirect('/success')
"""
@app.route('/register', methods=['GET','POST'])
def register():

    if request.method == 'GET':
        return render_template("register.html", batches=prepare_batches())

    try:
        data = request.form
        file = request.files.get('payment_proof')

        seat = data.get('seat')
        print("Selected seat:", seat)

        filename = None
        if file:
            filename = file.filename
            file.save(f"static/uploads/{filename}")

        batch_id = int(data.get('batch_id'))
        gender = data.get('gender')

        batch = db.session.get(Batch, batch_id)

        if not batch:
            return "Invalid batch"

        if batch.filled_slots >= batch.capacity:
            return "Batch is full"

        male_count = Student.query.filter_by(batch_id=batch.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=batch.id, gender="Female").count()

        if gender == "Male" and male_count >= 3:
            return "No seats for Male"

        if gender == "Female" and female_count >= 3:
            return "No seats for Female"

        # ✅ FIX AGE SAFELY
        age_input = data.get('age')
        try:
            age = int(age_input.replace(" Yrs", "").strip())
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

        # ✅ email sending
        threading.Thread(
            target=send_email,
            args=(
                data.get('email'),
                "Registration Successful ✅",
                "Your application has been submitted successfully."
            )
        ).start()

        return redirect('/success')

    except Exception as e:
        return f"ERROR: {str(e)}"   # ✅ DEBUG SAFE



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
@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect('/login')

    return render_template("admin.html",
                           students=Student.query.all(),
                           batches=Batch.query.all())

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
    s = Student.query.get(id)
    if s:
        s.payment_status = "Paid"
        db.session.commit()
    return "ok"

@app.route('/delete_student/<int:id>')
def delete_student(id):
    s = Student.query.get(id)
    if s:
        db.session.delete(s)
        db.session.commit()
    return "deleted"

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
    s = Student.query.get(id)

    file = f"certificate_{id}.pdf"
    c = canvas.Canvas(file)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, "Amrutha Aarogya Ayurvedic Hospital")

    c.setFont("Helvetica", 12)
    c.drawString(100, 700, f"This certifies {s.name}")
    c.drawString(100, 680, "has completed internship")
    c.drawString(100, 660, f"Batch: {s.batch_id}")

    c.save()
    return send_file(file, as_attachment=True)

# ---------------- RECEIPT ----------------
@app.route('/receipt/<int:id>')
def receipt(id):
    student = Student.query.get(id)
    return render_template("receipt.html", student=student)

# ---------------- RAZORPAY ----------------
rzp = razorpay.Client(auth=("rzp_test_T4zOfEFxtW3PGC", "9PMv70mWFMCreszQAmjlNKtA"))

@app.route('/create_order')
def create_order():
    order = rzp.order.create({
        "amount": 100000,  #₹1000 (in paise)
        "currency": "INR"
    })
    print(order)
    return jsonify(order)
    
@app.route('/verify_payment', methods=['POST'])
def verify_payment():
    data = request.json

    try:
        rzp.utility.verify_payment_signature({
            'razorpay_order_id': data['order_id'],
            'razorpay_payment_id': data['payment_id'],
            'razorpay_signature': data['signature']
        })

        student_id = data.get('student_id')
        s = Student.query.get(student_id)

        if s:
            s.payment_status = "Paid"
            db.session.commit()

        return {"status": "verified"}

    except Exception as e:
        print("Payment error:", e)
        return {"status": "failed"}

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


import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
