from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash
import razorpay
import csv
import pandas as pd
from reportlab.pdfgen import canvas
from datetime import datetime



app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DATABASE ----------------

# ✅ DATABASE CONFIG ONCE
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'

db = SQLAlchemy(app)

# ---------------- MODELS ----------------
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
    payment_status = db.Column(db.String(20), default="Pending")



# ---------------- ADMIN LOGIN ----------------
ADMIN_USER = "admin"
#ADMIN_PASS_HASH = "PASTE_YOUR_HASH_HERE"
ADMIN_PASS = "admin123"


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

# ---------------- HOME ----------------


# ---------------- REGISTER ----------------
"""
from datetime import datetime

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        #batch = Batch.query.get(int(request.form['batch_id']))
        batch = db.session.get(Batch, int(request.form.get('batch_id')))
        gender = request.form['gender']

        if not batch:
            return render_template(
                "register.html",
                error="Invalid batch",
                batches=prepare_batches()
            )

        # ✅ capacity check
        if batch.filled_slots >= batch.capacity:
            return render_template(
                "register.html",
                error="Batch is full",
                batches=prepare_batches()
            )

        # ✅ count seats
        male_count = Student.query.filter_by(batch_id=batch.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=batch.id, gender="Female").count()

        # ✅ gender slot check
        if gender == "Male" and male_count >= 3:
            return render_template(
                "register.html",
                error="No seats available for Male",
                batches=prepare_batches()
            )

        if gender == "Female" and female_count >= 3:
            return render_template(
                "register.html",
                error="No seats available for Female",
                batches=prepare_batches()
            )

        # ✅ save student
        student = Student(
        name=request.form.get('name'),
        email=request.form.get('email'),
        phone=request.form.get('phone'),
        age=request.form.get('age'),
        college=request.form.get('college'),
        pincode=request.form.get('pincode'),
        state=request.form.get('state'),
        district=request.form.get('district'),
        place=request.form.get('place'),
        batch_id=batch.id,
        gender=gender
    )


        batch.filled_slots += 1
        db.session.add(student)
        db.session.commit()

        return redirect(f"/success?student_id={student.id}")

    # ✅ ✅ ✅ THIS LINE FIXES YOUR ERROR
    return render_template("register.html", batches=prepare_batches())
"""

from datetime import datetime

@app.route('/register', methods=['GET','POST'])
def register():

    
# ✅ load page
    if request.method == 'GET':
        return render_template("register.html", batches=prepare_batches())


    data = request.json   # ✅ read JSON (NOT form anymore)

    batch_id = int(data.get('batch_id'))
    gender = data.get('gender')

    batch = db.session.get(Batch, batch_id)

    if not batch:
        return {"status": "error", "message": "Invalid batch"}

    # ✅ capacity check
    if batch.filled_slots >= batch.capacity:
        return {"status": "error", "message": "Batch is full"}

    # ✅ gender seat check
    male_count = Student.query.filter_by(batch_id=batch.id, gender="Male").count()
    female_count = Student.query.filter_by(batch_id=batch.id, gender="Female").count()

    if gender == "Male" and male_count >= 3:
        return {"status": "error", "message": "No seats for Male"}

    if gender == "Female" and female_count >= 3:
        return {"status": "error", "message": "No seats for Female"}

    # ✅ NOW SAVE STUDENT (AFTER PAYMENT SUCCESS)
    student = Student(
        name=data.get('name'),
        email=data.get('email'),
        phone=data.get('phone'),
        age=data.get('age'),
        college=data.get('college'),
        pincode=data.get('pincode'),
        state=data.get('state'),
        district=data.get('district'),
        place=data.get('place'),
        batch_id=batch.id,
        gender=gender,
        payment_status="Paid"
    )

    batch.filled_slots += 1

    db.session.add(student)
    db.session.commit()

    return {"status": "success", "student_id": student.id}


##----------------------Batches------------------------------------------------------ 
def prepare_batches():
    #batches = Batch.query.all()
    batches = Batch.query.order_by(Batch.start_date).all()
    grouped = {}

    for b in batches:
        try:
            start = datetime.strptime(b.start_date, "%Y-%m-%d")
            end = datetime.strptime(b.end_date, "%Y-%m-%d")
        except:
            
            print("Skipping invalid batch:", b.start_date, b.end_date)
            continue 

        month = start.strftime('%B')

        if month not in grouped:
            grouped[month] = {
                "start": start,
                "end": end,
                "ids": [b.id],
                "male": 0,
                "female": 0
            }
        else:
            grouped[month]["end"] = max(grouped[month]["end"], end)
            grouped[month]["ids"].append(b.id)

        male_count = Student.query.filter_by(batch_id=b.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=b.id, gender="Female").count()

        grouped[month]["male"] += male_count
        grouped[month]["female"] += female_count

    result = []

    for month, data in grouped.items():

        male_left = max(0, 6 - data["male"])
        female_left = max(0, 6 - data["female"])

        #label = f"{month} ({data['start'].day} – {data['end'].day}) (👨 {male_left} | 👩 {female_left} left)"
        label = f"{start.strftime('%B %Y')} ({start.day} – {end.day}) (👨 {male_left} | 👩 {female_left} left)"


        result.append({
            "id": data["ids"][0],   # pick first batch id
            "label": label,
            "male_left": male_left,
            "female_left": female_left
        })

    return result



    #return render_template("register.html", batches=Batch.query.all())

# ---------------- SUCCESS ----------------
@app.route('/success')
def success():
    return render_template("success.html")

# ---------------- ADMIN DASHBOARD ----------------
@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect('/login')

    return render_template("admin.html",
                           students=Student.query.all(),
                           batches=Batch.query.all())


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
@app.route('/export_excel')
def export_excel():
    data = [{
        "Name": s.name,
        "Email": s.email,
        "Phone": s.phone,
        "College": s.college,
        "Batch": s.batch_id,
        "Status": s.payment_status
    } for s in Student.query.all()]

    df = pd.DataFrame(data)
    path = "report.xlsx"
    df.to_excel(path, index=False)

    return send_file(path, as_attachment=True)

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
    if Batch.query.count() == 0:

        year = datetime.now().year

        for month in range(1, 13):

            last_day = calendar.monthrange(year, month)[1]

            start_date = f"{year}-{month:02d}-01"
            end_date = f"{year}-{month:02d}-{last_day}"

            db.session.add(Batch(
                start_date=start_date,
                end_date=end_date,
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
        label = f"{start.strftime('%B %Y')} ({start.day} – {end.day}) (👨 {male_left} | 👩 {female_left} left)"

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

import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
