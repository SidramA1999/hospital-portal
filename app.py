from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text
import razorpay
import csv
import pandas as pd
from reportlab.pdfgen import canvas
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
import threading
import io
import os
import json
import calendar

app = Flask(__name__)

# NOTE: raised from 5MB -> 12MB. A single registration now uploads TWO
# files in the same request (passport photo + payment screenshot), each
# individually capped at 5MB on the frontend. The old 5MB limit applied
# to the WHOLE request, so two normal-sized files together could get
# silently rejected by Flask with a 413 error before your route code
# ever ran.
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024

if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")

if not os.path.exists("static/gallery"):
    os.makedirs("static/gallery")

if not os.path.exists("static/uploads/photos"):
    os.makedirs("static/uploads/photos")

app.secret_key = os.getenv("SECRET_KEY", "fallback123")

# ---------------- DATABASE ----------------
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


# ---------------- GALLERY TAXONOMY (fixed, not admin-editable) ----------------
# Replaces the old open-ended Category CRUD system. A small, stable list
# defined by the hospital's own structure doesn't need per-category
# add/edit/delete — it needs to just be right, once. Category keys (left)
# are what's actually stored on Gallery.category; labels/icons are what
# the UI shows.
GALLERY_TAXONOMY = {
    "hospital": {
        "label": "Hospital Infrastructure", "icon": "🏥",
        "subcategories": ["Building", "OPD", "IPD", "Pharmacy"],
    },
    "doctors": {
        "label": "Doctors & Faculty", "icon": "👨‍⚕️",
        "subcategories": ["Doctors", "Faculty", "Clinical Training"],
    },
    "panchakarma": {
        "label": "Panchakarma", "icon": "🌿",
        "subcategories": ["Vamana", "Virechana", "Basti", "Therapies"],
    },
    "internship": {
        "label": "Internship & Students", "icon": "🎓",
        "subcategories": ["Interns", "Practical Sessions", "Student Activities"],
    },
    "events": {
        "label": "Events & Workshops", "icon": "🎉",
        "subcategories": ["Seminars", "Workshops", "Conferences"],
    },
}


# ---------------- MODELS ----------------
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(10), default='🖼️')
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    event_date = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Gallery(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    category = db.Column(db.String(50))          # legacy string category — kept for backward compatibility
    title = db.Column(db.String(200))
    image = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    media_type = db.Column(db.String(10), default='photo')   # 'photo' | 'video' | 'youtube'
    description = db.Column(db.Text)
    subcategory = db.Column(db.String(100))       # e.g. "Vamana" within category "panchakarma"
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    external_url = db.Column(db.String(500))
    thumbnail = db.Column(db.String(255))
    featured = db.Column(db.Boolean, default=False)
    is_visible = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    is_archived = db.Column(db.Boolean, default=False)

    category_ref = db.relationship('Category', backref='media')
    batch_ref = db.relationship('Batch', backref='media')
    event_ref = db.relationship('Event', backref='media')


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

    age = db.Column(db.Integer)
    dob = db.Column(db.String(20))   # source of truth going forward; age is derived from this
    college = db.Column(db.String(100))

    pincode = db.Column(db.String(10))
    state = db.Column(db.String(100))
    district = db.Column(db.String(100))
    place = db.Column(db.String(100))

    batch_id = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    seat = db.Column(db.String(10))
    transaction_id = db.Column(db.String(100))
    payment_proof = db.Column(db.String(200))
    photo = db.Column(db.String(255))
    payment_status = db.Column(db.String(20), default="Pending")
    application_status = db.Column(db.String(20), default="Pending")
    completion_status = db.Column(db.String(20), default="In Progress")

    __table_args__ = (
        db.UniqueConstraint('batch_id', 'seat', name='uq_batch_seat'),
    )


class SiteStat(db.Model):
    """A tiny key-value table for counters that need to survive
    restarts/redeploys — starting with the homepage visit count, which
    was previously a plain Python variable (`visits = 0`) that reset
    to zero every time the app restarted, losing the real count."""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Integer, default=0)


# ---------------- ADMIN LOGIN ----------------
ADMIN_USER = "Tukaram"
ADMIN_PASS = "#Samhita@1414"


@app.route('/login', methods=['GET', 'POST'])
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


@app.route("/check_status", methods=["POST"])
def check_status():
    data = request.get_json()
    query = data.get("query")

    student = Student.query.filter(
        (Student.phone == query) |
        (Student.name.ilike(f"%{query}%"))
    ).first()

    if not student:
        return {"status": "Not Found"}

    return {"status": student.application_status}


# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'GET':
        return render_template("register.html", batches=prepare_batches())

    try:
        data = request.form
        file = request.files.get('payment_proof')
        photo_file = request.files.get("student_photo")

        if photo_file:
            if photo_file.content_length and (photo_file.content_length > 5 * 1024 * 1024):
                return "Photo size exceeds 5 MB"

        seat = data.get('selected_seat')
        if not seat:
            return "Please select a seat"
        gender = data.get('gender')

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

        male_count = Student.query.filter_by(batch_id=batch.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=batch.id, gender="Female").count()

        if gender == "Male" and male_count >= 3:
            return "No seats available for Male"
        if gender == "Female" and female_count >= 3:
            return "No seats available for Female"

        try:
            age = int(data.get('age', '0').replace(" Yrs", "").strip())
        except Exception:
            age = 0

        existing_seat = Student.query.filter_by(batch_id=batch.id, seat=seat).first()
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
            transaction_id=data.get('transaction_id'),
            payment_proof=filename,
            photo=photo_filename,
            payment_status="Pending"
        )

        batch.filled_slots += 1
        db.session.add(student)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            batch.filled_slots -= 1
            return f"Sorry, seat {seat} was just taken — please choose another"

        session["student_id"] = student.id
        print("Saved Student ID:", student.id)

        application_id = f"AAK-{student.id:05d}"

        photo_block = ""
        if student.photo:
            photo_url = f"{request.url_root.rstrip('/')}/static/uploads/photos/{student.photo}"
            photo_block = f"""
            <div style="text-align:center;">
                <img src="{photo_url}" alt="Student Photo" width="120" height="140"
                    style="width:120px;height:140px;border-radius:10px;border:3px solid #cf9f45;object-fit:cover;">
            </div>
            <br>
            """

        email_message = f"""
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f8f4;padding:20px;">
        <div style="max-width:700px;margin:auto;background:white;padding:30px;border-radius:15px;border:1px solid #ddd;">
        <h2 style="text-align:center;color:#0f3a29;">🌿 Amrutha Aarogya Kendra</h2>
        <h3 style="text-align:center;color:#cf9f45;">Internship Application Received</h3>
        <p>Dear <b>{student.name}</b>,</p>
        <p>Thank you for applying for our Internship Program. Your application has been successfully received.</p>
        <div style="background:#e6f7ec;padding:15px;border-radius:10px;text-align:center;">
        <h3>Application ID</h3>
        <h2 style="color:#0f3a29;">{application_id}</h2>
        </div>
        <br>
        {photo_block}
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
        <p>Your application has been forwarded to our Internship Committee for verification.</p>
        <p>Once the verification process is completed, you will receive another email regarding your admission status.</p>
        <p>Please save your Application ID for future reference.</p>
        <hr>
        <p><b>Need Help?</b><br>📞 +91 97421 51414<br>📱 WhatsApp: +91 99168 03734</p>
        <p>Warm Regards,<br><b>Dr. Tukaram Umarani</b><br>Ayurvedacharya<br>Amrutha Aarogya Kendra Ayurvedic Hospital</p>
        </div>
        </body>
        </html>
        """

        threading.Thread(
            target=send_email,
            args=(student.email, "Training Application Received ✅", email_message)
        ).start()

        return redirect(f'/success/{student.id}')

    except Exception as e:
        db.session.rollback()
        print("REGISTER ERROR:", str(e))
        return f"ERROR: {str(e)}"


# ---------------- DEBUG (admin-only) ----------------
@app.route("/debug_students")
def debug_students():
    if not session.get('admin'):
        return redirect('/login')
    students = Student.query.all()
    return jsonify([
        {"id": s.id, "name": s.name, "batch_id": s.batch_id, "gender": s.gender, "seat": s.seat}
        for s in students
    ])


@app.route("/debug_batch/<int:batch_id>")
def debug_batch(batch_id):
    if not session.get('admin'):
        return redirect('/login')
    students = Student.query.filter_by(batch_id=batch_id).all()
    return jsonify([
        {"id": s.id, "name": s.name, "gender": s.gender, "seat": s.seat}
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

    booked_students = Student.query.filter_by(batch_id=batch_id).all()
    for student in booked_students:
        if student.seat in seats:
            seats[student.seat]["booked"] = True

    male_available = sum(1 for s in seats.values() if s["gender"] == "Male" and not s["booked"])
    female_available = sum(1 for s in seats.values() if s["gender"] == "Female" and not s["booked"])

    return jsonify({
        "batch_id": batch_id,
        "seats": seats,
        "male_available": male_available,
        "female_available": female_available
    })


@app.route("/success/<int:student_id>")
def success(student_id):

    student = Student.query.get_or_404(student_id)

    application_id = f"AAK-{student.id:05d}"

    batch = db.session.get(Batch, student.batch_id) if student.batch_id else None

    batch_start_fmt = None
    batch_end_fmt = None
    duration_days = None

    if batch and batch.start_date and batch.end_date:

        if hasattr(batch.start_date, "strftime"):
            batch_start_fmt = batch.start_date.strftime("%d %b %Y")
            batch_end_fmt = batch.end_date.strftime("%d %b %Y")

            duration_days = (
                batch.end_date - batch.start_date
            ).days + 1

        else:
            try:
                start_dt = datetime.strptime(batch.start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(batch.end_date, "%Y-%m-%d")

                batch_start_fmt = start_dt.strftime("%d %b %Y")
                batch_end_fmt = end_dt.strftime("%d %b %Y")

                duration_days = (end_dt - start_dt).days + 1

            except ValueError:
                batch_start_fmt = batch.start_date
                batch_end_fmt = batch.end_date

    return render_template(
        "success.html",
        student=student,
        application_id=application_id,
        batch_start=batch_start_fmt,
        batch_end=batch_end_fmt,
        reporting_date=batch_start_fmt,
        duration_days=duration_days,
    )

# ---------------- AI CHAT ----------------
from openai import OpenAI
client = OpenAI(api_key="YOUR_API_KEY")


@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.json.get("message")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Answer ONLY from hospital training rules. If outside, say: Please contact hospital 📞"},
            {"role": "user", "content": user_msg}
        ]
    )
    return {"reply": response.choices[0].message.content}


# ---------------- ADMIN DASHBOARD ----------------
@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect('/login')

    today = datetime.today()
    all_batches = Batch.query.all()

    batches = []
    for b in all_batches:
        b.filled_slots = Student.query.filter_by(batch_id=b.id).count()

    for b in all_batches:
        try:
            end_date = datetime.strptime(b.end_date, "%Y-%m-%d")
            if end_date < today:
                continue
            b.start_display = datetime.strptime(b.start_date, "%Y-%m-%d").strftime("%d-%b-%Y")
            b.end_display = datetime.strptime(b.end_date, "%Y-%m-%d").strftime("%d-%b-%Y")
            batches.append(b)
        except Exception:
            continue

    return render_template(
        "admin.html",
        students=Student.query.all(),
        batches=batches,
        media=Gallery.query.order_by(Gallery.id.desc()).all(),
        events=Event.query.order_by(Event.id.desc()).all(),
        taxonomy=GALLERY_TAXONOMY,
        taxonomy_json=json.dumps(GALLERY_TAXONOMY),
    )


@app.route("/all_candidates")
def all_candidates():
    if not session.get('admin'):
        return redirect('/login')
    students = Student.query.order_by(Student.id.asc()).all()
    return render_template("all_candidates.html", students=students)


# ---------------- ADMIN: MANUALLY ADD STUDENT ----------------
def calculate_age_from_dob(dob_str, fmt="%Y-%m-%d"):
    """Single source of truth for age math, used wherever a DOB needs
    turning into an age (currently: manual student add). dob_str is
    whatever format the calling form's date input sends."""
    try:
        dob = datetime.strptime(dob_str, fmt)
    except (TypeError, ValueError):
        return None
    today = datetime.today()
    age = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    return age


@app.route('/admin/add_student', methods=['POST'])
def admin_add_student():
    if not session.get('admin'):
        return redirect('/login')

    try:
        batch_id = int(request.form.get('batch_id'))
    except (TypeError, ValueError):
        return "Please choose a batch"

    gender = request.form.get('gender')
    batch = db.session.get(Batch, batch_id)
    if not batch:
        return "Invalid batch"
    if gender not in ("Male", "Female"):
        return "Please choose a gender"

    prefix = 'MX' if gender == 'Male' else 'FX'
    existing_extra = Student.query.filter(
        Student.batch_id == batch_id,
        Student.seat.like(f'{prefix}%')
    ).count()
    seat_label = f"{prefix}{existing_extra + 1}"

    # DOB is the field of record; age is derived from it (never typed
    # directly), so it can never go stale or be mistyped.
    dob = request.form.get('dob')
    age = calculate_age_from_dob(dob) if dob else None

    student = Student(
        name=request.form.get('name'),
        email=request.form.get('email'),
        phone=request.form.get('phone'),
        dob=dob,
        age=age,
        college=request.form.get('college'),
        batch_id=batch_id,
        gender=gender,
        seat=seat_label,
        payment_status=request.form.get('payment_status') or 'Pending',
    )

    batch.filled_slots += 1
    db.session.add(student)
    db.session.commit()

    return redirect('/admin#students')


@app.route('/gallery_admin', methods=['GET', 'POST'])
def gallery_admin():
    if request.method == 'POST':
        category = request.form['category']
        title = request.form['title']
        file = request.files['image']
        filename = secure_filename(file.filename)
        file.save(f"static/gallery/{filename}")
        img = Gallery(category=category, title=title, image=filename)
        db.session.add(img)
        db.session.commit()

    images = Gallery.query.all()
    return render_template("gallery_admin.html", images=images)


# ---------------- MEDIA LIBRARY ----------------
@app.route('/admin/media/add', methods=['POST'])
def add_media():
    if not session.get('admin'):
        return jsonify({"status": "error", "message": "Not authorized"}), 403
    try:
        # Media type is auto-detected client-side from the file's MIME
        # type and sent as this field — the admin never has to pick it
        # from a dropdown.
        media_type = request.form.get('media_type', 'photo')
        title = request.form.get('title')

        category = request.form.get('category') or None          # e.g. "panchakarma"
        subcategory = request.form.get('subcategory') or None     # e.g. "Vamana"
        if category and category not in GALLERY_TAXONOMY:
            return jsonify({"status": "error", "message": "Unknown category"}), 400

        # Optional metadata — never required, tucked away in the UI
        batch_id = request.form.get('batch_id') or None
        event_id = request.form.get('event_id') or None
        external_url = request.form.get('external_url')

        filename = None
        if media_type in ('photo', 'video'):
            file = request.files.get('file')
            if not file or not file.filename:
                return jsonify({"status": "error", "message": "Please choose a file to upload"}), 400
            filename = f"{media_type}_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            file.save(f"static/gallery/{filename}")
        elif media_type == 'youtube':
            if not external_url:
                return jsonify({"status": "error", "message": "Please provide a YouTube URL"}), 400

        item = Gallery(
            media_type=media_type,
            title=title,
            category=category,
            subcategory=subcategory,
            image=filename,
            external_url=external_url if media_type == 'youtube' else None,
            batch_id=int(batch_id) if batch_id else None,
            event_id=int(event_id) if event_id else None,
            # Upload always lands visible and un-featured — "featured"
            # (show on homepage) is now a one-tap star toggle on the
            # already-uploaded card, done after the fact, not decided
            # under time pressure during upload.
            featured=False,
            is_visible=True,
            display_order=0,
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({"status": "success", "id": item.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/media/edit/<int:id>', methods=['POST'])
def edit_media(id):
    if not session.get('admin'):
        return jsonify({"status": "error", "message": "Not authorized"}), 403
    item = db.session.get(Gallery, id)
    if not item:
        return jsonify({"status": "error", "message": "Not found"}), 404
    try:
        item.title = request.form.get('title', item.title)
        category = request.form.get('category')
        subcategory = request.form.get('subcategory')
        if category:
            if category not in GALLERY_TAXONOMY:
                return jsonify({"status": "error", "message": "Unknown category"}), 400
            item.category = category
            item.subcategory = subcategory or None
        batch_id = request.form.get('batch_id')
        event_id = request.form.get('event_id')
        item.batch_id = int(batch_id) if batch_id else None
        item.event_id = int(event_id) if event_id else None

        file = request.files.get('file')
        if file and file.filename:
            filename = f"{item.media_type}_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            file.save(f"static/gallery/{filename}")
            item.image = filename

        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/media/toggle/<int:id>/<field>')
def toggle_media_field(id, field):
    if not session.get('admin'):
        return redirect('/login')
    item = db.session.get(Gallery, id)
    if item:
        if field == 'featured':
            item.featured = not item.featured
        elif field == 'visible':
            item.is_visible = not item.is_visible
        elif field == 'archive':
            item.is_archived = not item.is_archived
        db.session.commit()
    return "ok"


@app.route('/admin/media/delete/<int:id>')
def delete_media(id):
    if not session.get('admin'):
        return redirect('/login')
    item = db.session.get(Gallery, id)
    if item:
        db.session.delete(item)
        db.session.commit()
    return "deleted"


@app.route('/admin/events/add', methods=['POST'])
def add_event():
    if not session.get('admin'):
        return redirect('/login')
    name = request.form.get('name', '').strip()
    event_date = request.form.get('event_date', '')
    if name:
        db.session.add(Event(name=name, event_date=event_date))
        db.session.commit()
    return "ok"


@app.route('/admin/events/delete/<int:id>')
def delete_event(id):
    if not session.get('admin'):
        return redirect('/login')
    e = db.session.get(Event, id)
    if e:
        Gallery.query.filter_by(event_id=e.id).update({Gallery.event_id: None})
        db.session.delete(e)
        db.session.commit()
    return "deleted"


@app.route('/seat_status')
def seat_status():
    data = {}
    batches = Batch.query.order_by(Batch.start_date).all()
    for b in batches:
        male_count = Student.query.filter_by(batch_id=b.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=b.id, gender="Female").count()
        data[b.id] = {"male_left": 3 - male_count, "female_left": 3 - female_count}
    return jsonify(data)


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
        except Exception:
            continue

    new_batch = Batch(start_date=start, end_date=end, capacity=int(request.form['capacity']), filled_slots=0)
    db.session.add(new_batch)
    db.session.commit()
    return redirect('/admin')


@app.route('/edit_batch/<int:id>/<start>/<end>/<int:cap>')
def edit_batch(id, start, end, cap):
    b = Batch.query.get(id)
    if b:
        b.start_date = start
        b.end_date = end
        b.capacity = cap
        db.session.commit()
    return "updated"


@app.route('/delete_batch/<int:id>')
def delete_batch(id):
    b = Batch.query.get(id)
    if b:
        db.session.delete(b)
        db.session.commit()
    return "deleted"


@app.route('/gallery')
def gallery():
    # No filters to compute or pass anymore — the page just needs the
    # media itself, grouped by category then subcategory. Empty
    # categories are left out entirely so the page never shows an
    # empty "Events & Workshops" section with nothing under it.
    all_media = Gallery.query.filter_by(is_visible=True, is_archived=False) \
                              .order_by(Gallery.id.desc()).all()

    grouped = {}
    for key, info in GALLERY_TAXONOMY.items():
        items = [m for m in all_media if m.category == key]
        if not items:
            continue
        subs = {}
        for m in items:
            subs.setdefault(m.subcategory or "General", []).append(m)
        grouped[key] = {"label": info["label"], "icon": info["icon"], "subs": subs}

    return render_template("gallery.html", grouped=grouped)


@app.route('/student/<int:id>')
def student_detail(id):
    if not session.get('admin'):
        return redirect('/login')
    student = Student.query.get(id)
    batch = Batch.query.get(student.batch_id)
    return render_template('student_detail.html', student=student, batch=batch)


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


@app.route('/mark_completed/<int:id>')
def mark_completed(id):
    s = db.session.get(Student, id)
    if s:
        s.completion_status = "Completed"
        if s.application_status != "Approved":
            s.application_status = "Approved"
        db.session.commit()
    return "ok"


@app.route('/delete_student/<int:id>')
def delete_student(id):
    s = db.session.get(Student, id)
    if s:
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


@app.route('/fix_batch_counts')
def fix_batch_counts():
    for batch in Batch.query.all():
        batch.filled_slots = Student.query.filter_by(batch_id=batch.id).count()
    db.session.commit()
    return "Batch counts fixed ✅"


@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    file = request.files['file']
    reader = csv.reader(file.stream.read().decode("UTF-8").splitlines())
    next(reader)
    for r in reader:
        db.session.add(Student(
            name=r[0], email=r[1], phone=r[2], college=r[3],
            batch_id=int(r[4]), payment_status="Pending"
        ))
    db.session.commit()
    return redirect('/admin')


@app.route('/export_excel')
def export_excel():
    try:
        data = [{
            "Date": datetime.now().strftime("%Y-%m-%d"),
            "Name": s.name, "Email": s.email, "Phone": s.phone,
            "College": s.college, "Seat": s.seat, "Gender": s.gender,
            "Batch": s.batch_id, "Status": s.application_status
        } for s in Student.query.all()]

        if not data:
            return "No student data available"

        df = pd.DataFrame(data)
        output = io.BytesIO()
        df.to_excel(output, index=False, engine="openpyxl")
        output.seek(0)

        return send_file(
            output, as_attachment=True, download_name="students.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return str(e)


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
        buffer, as_attachment=True,
        download_name=f"Amruta Arogya Kendra Training Certificate - {s.name}.pdf",
        mimetype="application/pdf",
    )


@app.route('/certificate/blank')
def certificate_blank():
    if not session.get('admin'):
        return redirect('/login')

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    draw_certificate(
        c, width, height,
        student_name="_______________________",
        training_type="AYURVEDIC INTERNSHIP TRAINING",
        batch_start="__________",
        batch_end="__________",
        logo_path="static/logo.jpg",
        seal_path="static/seal.png",
    )
    c.showPage()
    c.save()
    buffer.seek(0)

    return send_file(
        buffer, as_attachment=True,
        download_name="Amruta_Arogya_Kendra_Blank_Certificate_Template.pdf",
        mimetype="application/pdf",
    )


@app.route('/admin/quick_certificate', methods=['POST'])
def quick_certificate():
    if not session.get('admin'):
        return redirect('/login')

    name = request.form.get('name', '').strip()
    if not name:
        return "Name is required"

    training_type = request.form.get('training_type') or "Ayurvedic Internship Training"
    batch_start = request.form.get('batch_start') or "N/A"
    batch_end = request.form.get('batch_end') or "N/A"

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    draw_certificate(
        c, width, height,
        student_name=name,
        training_type=training_type,
        batch_start=batch_start,
        batch_end=batch_end,
        logo_path="static/logo.jpg",
        seal_path="static/seal.png",
    )
    c.showPage()
    c.save()
    buffer.seek(0)

    return send_file(
        buffer, as_attachment=True,
        download_name=f"Amruta Arogya Kendra Training Certificate - {name}.pdf",
        mimetype="application/pdf",
    )


@app.route('/receipt/<int:id>')
def receipt(id):
    student = Student.query.get(id)
    return render_template("receipt.html", student=student)


@app.route('/')
def home():
    # Persistent counter — survives restarts/redeploys, unlike the old
    # `visits = 0` global Python variable which reset to zero every
    # time the app process restarted (which happens on every deploy,
    # and on many hosts also on idle-sleep/scale events).
    stat = SiteStat.query.filter_by(key='visits').first()
    if not stat:
        # First time this new persistent counter is ever created — seed
        # it with your current count instead of starting over at zero.
        # Set INITIAL_VISIT_COUNT to whatever number your site shows
        # right now, deploy once, then you can remove the env var —
        # it's only read on this one-time creation of the row.
        starting_value = int(os.getenv("INITIAL_VISIT_COUNT", "0"))
        stat = SiteStat(key='visits', value=starting_value)
        db.session.add(stat)
    stat.value += 1
    db.session.commit()
    visits = stat.value

    featured_media = Gallery.query.filter_by(featured=True, is_visible=True, is_archived=False) \
                                   .order_by(Gallery.display_order).limit(6).all()
    if not featured_media:
        featured_media = Gallery.query.filter_by(is_visible=True, is_archived=False) \
                                       .order_by(Gallery.id.desc()).limit(6).all()

    return render_template("index.html", visits=visits, featured_media=featured_media)


def create_initial_batches():
    year = datetime.now().year
    for month in range(1, 13):
        last_day = calendar.monthrange(year, month)[1]
        start1 = f"{year}-{month:02d}-01"
        end1 = f"{year}-{month:02d}-{last_day}"
        if not Batch.query.filter_by(start_date=start1).first():
            db.session.add(Batch(start_date=start1, end_date=end1, capacity=6, filled_slots=0))

        if month == 12:
            next_month, next_year = 1, year + 1
        else:
            next_month, next_year = month + 1, year

        start2 = f"{year}-{month:02d}-15"
        end2 = f"{next_year}-{next_month:02d}-14"
        if not Batch.query.filter_by(start_date=start2).first():
            db.session.add(Batch(start_date=start2, end_date=end2, capacity=6, filled_slots=0))

    db.session.commit()


def prepare_batches():
    batches = Batch.query.order_by(Batch.start_date).all()
    result = []
    today = datetime.today()
    current_month = datetime(today.year, today.month, 1)

    if today.month == 12:
        limit_month = datetime(today.year + 1, 2, 1)
    elif today.month == 11:
        limit_month = datetime(today.year + 1, 1, 1)
    else:
        limit_month = datetime(today.year, today.month + 2, 1)

    for b in batches:
        try:
            start = datetime.strptime(b.start_date, "%Y-%m-%d")
            end = datetime.strptime(b.end_date, "%Y-%m-%d")
        except Exception:
            continue

        if hasattr(b, "is_active") and not b.is_active:
            continue
        if start < current_month:
            continue
        if start >= limit_month:
            continue

        male_count = Student.query.filter_by(batch_id=b.id, gender="Male").count()
        female_count = Student.query.filter_by(batch_id=b.id, gender="Female").count()

        result.append({
            "id": b.id,
            "label": f"{start.strftime('%d %b')} → {end.strftime('%d %b')}",
            "male_left": max(0, 3 - male_count),
            "female_left": max(0, 3 - female_count)
        })

    return result


@app.route('/auto_batches')
def auto_batches():
    # Referenced by the "Auto Generate" button in Admin -> Quick Actions,
    # which had no matching route at all (a dead link, 404 on click).
    # Reuses the same batch-generation logic already run at startup.
    if not session.get('admin'):
        return redirect('/login')
    create_initial_batches()
    return redirect('/admin')


@app.route('/toggle_batch/<int:id>')
def toggle_batch(id):
    if not session.get('admin'):
        return redirect('/login')
    batch = Batch.query.get_or_404(id)
    batch.is_active = not batch.is_active
    db.session.commit()
    return redirect('/admin')


def ensure_gallery_columns():
    inspector = inspect(db.engine)
    existing_cols = {c['name'] for c in inspector.get_columns('gallery')}
    new_cols = {
        'media_type':    "VARCHAR(10) DEFAULT 'photo'",
        'description':   "TEXT",
        'subcategory':   "VARCHAR(100)",
        'category_id':   "INTEGER",
        'batch_id':      "INTEGER",
        'event_id':      "INTEGER",
        'external_url':  "VARCHAR(500)",
        'thumbnail':     "VARCHAR(255)",
        'featured':      "BOOLEAN DEFAULT FALSE",
        'is_visible':    "BOOLEAN DEFAULT TRUE",
        'display_order': "INTEGER DEFAULT FALSE",
        'is_archived':   "BOOLEAN DEFAULT 0",
    }
    with db.engine.connect() as conn:
        for col, coltype in new_cols.items():
            if col not in existing_cols:
                conn.execute(text(f"ALTER TABLE gallery ADD COLUMN {col} {coltype}"))
        conn.commit()


def ensure_student_columns():
    """Same reasoning as ensure_gallery_columns — the `dob` column is new
    on an existing `student` table, so it needs an explicit ALTER TABLE
    rather than relying on db.create_all()."""
    inspector = inspect(db.engine)
    existing_cols = {c['name'] for c in inspector.get_columns('student')}
    if 'dob' not in existing_cols:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE student ADD COLUMN dob VARCHAR(20)"))
            conn.commit()


def ensure_gallery_category_remap():
    """The original hardcoded categories used the key 'interns'; the new
    fixed taxonomy (GALLERY_TAXONOMY) calls the same thing 'internship'.
    Without this, any photo uploaded under the old key would silently
    stop appearing anywhere in the redesigned gallery. Safe to run every
    startup — it only touches rows that still have the old key.
    """
    Gallery.query.filter_by(category="interns").update({Gallery.category: "internship"})

    # Photos uploaded through the PREVIOUS Media Library version (before
    # the taxonomy redesign) stored a category_id (foreign key to the
    # now-retired Category table) instead of the plain `category` string
    # this version actually reads — meaning every one of those existing
    # photos would silently vanish from the gallery, with no error and
    # no indication why. This recovers the ones that map cleanly onto
    # the new 5 fixed categories (the ones this app auto-created by
    # default); anything with a custom category name someone typed in
    # by hand can't be guessed automatically and is left for the admin
    # to fix with the "🏷️ Set Category" button on that card instead —
    # visible and fixable, rather than silently dropped.
    name_to_key = {
        "hospital infrastructure": "hospital",
        "clinical training": "doctors",
        "student life": "internship",
        "events": "events",
        "panchakarma": "panchakarma",
    }
    orphaned = Gallery.query.filter(
        Gallery.category.is_(None),
        Gallery.category_id.isnot(None)
    ).all()
    for row in orphaned:
        cat = db.session.get(Category, row.category_id)
        if cat and cat.name.strip().lower() in name_to_key:
            row.category = name_to_key[cat.name.strip().lower()]

    db.session.commit()


with app.app_context():
    db.create_all()
    ensure_gallery_columns()
    ensure_gallery_category_remap()
    ensure_student_columns()

    if not Batch.query.first():
        create_initial_batches()


import resend
resend.api_key = os.getenv("RESEND_API_KEY")


def send_email(to_email, subject, message):
    try:
        resend.Emails.send({
            "from": "onboarding@resend.dev",
            "to": [to_email],
            "subject": subject,
            "html": message
        })
        print("✅ Email sent successfully")
    except Exception as e:
        print("❌ Email failed:", e)


# -------------------- CERTIFICATE GENERATOR --------------------
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


def _wrap_text(c, text, font, size, max_width):
    """Greedy word-wrap to a fixed pixel width. This is what actually
    fixes the ragged-looking certificate paragraph: instead of manually
    hardcoded line breaks (which have no relationship to how wide each
    line actually renders, and get worse the longer training_type or
    the dates are), this fills every line as close to max_width as
    possible, so the centered block reads as one clean rectangle
    instead of a jagged staircase of very different line lengths."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if c.stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_certificate(
    c, width, height, *,
    student_name, trainee_photo=None, training_type, batch_start, batch_end,
    doctor_name="Dr. Tukaram B Umarani", doctor_cred="MS (Ayu)",
    hospital_line1="AMRUTA AAROGYA KENDRA,",
    hospital_line2="SPECIALITY AYURVEDA HOSPITAL, KALLOLI",
    address_lines=None, name_prefix="", cert_no=None, issue_date=None,
    logo_path="static/logo.jpg", seal_path="static/seal.png",
):
    if address_lines is None:
        address_lines = [
            "Amruta Aarogya Kendra,",
            "Speciality Ayurveda Hospital",
            "Kalloli-591224 Tq: Mudalagi",
            "Dist: Belagavi Mob: 9742151414",
        ]

    c.setFillColorRGB(*CREAM)
    c.rect(0, 0, width, height, stroke=0, fill=1)

    outer = 18
    inner = 27

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

    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(1.2)
    c.rect(outer, outer, width - 2 * outer, height - 2 * outer, stroke=1, fill=0)

    c.setStrokeColorRGB(*NAVY)
    c.setLineWidth(1.8)
    c.rect(inner, inner, width - 2 * inner, height - 2 * inner, stroke=1, fill=0)

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

    seal_r = 46
    seal_cy = height - 100
    if logo_path:
        try:
            img = ImageReader(logo_path)
            c.drawImage(img, cx - seal_r, seal_cy - seal_r, width=seal_r * 2, height=seal_r * 2,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    c.setFillColorRGB(*GOLD)
    c.setFont("Times-Bold", 17)
    c.drawCentredString(cx, height - 170, hospital_line1)
    c.setFont("Times-Bold", 11.5)
    c.drawCentredString(cx, height - 187, hospital_line2)

    _draw_spaced_centered(c, "CERTIFICATE", "Times-Bold", 42, cx, height - 246, 4.5, NAVY)
    _draw_spaced_centered(c, f"OF {training_type.upper()}", "Helvetica-Bold", 11.5, cx, height - 272, 2.2, GOLD)

    c.setFillColorRGB(*INK)
    c.setFont("Times-Italic", 15)
    c.drawCentredString(cx, height - 306, "This is to certify that")

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

    body_text = (
        f"has undergone and successfully completed a hands-on training in {training_type} "
        f"under the expert guidance of {doctor_name}. {doctor_cred}, at "
        f"{hospital_line1.rstrip(',').title()}, {hospital_line2.title()} during the period "
        f"of From {batch_start} to {batch_end}. Provided in depth exposure to classical "
        f"Ayurveda procedures and Patient care, enhancing one's own Practical knowledge "
        f"and Clinical skills."
    )
    c.setFillColorRGB(*INK)
    body_font, body_size = "Helvetica", 11.5
    c.setFont(body_font, body_size)
    body_max_width = width - 2 * inner - 130   # generous side margins, well clear of the border
    body_lines = _wrap_text(c, body_text, body_font, body_size, body_max_width)

    y = height - 375
    for line in body_lines:
        c.drawCentredString(cx, y, line)
        y -= 17.5

    # =========================================================
    # FOOTER — two balanced columns instead of everything stacked left.
    # LEFT  = identity of who's being certified (photo + straddling seal)
    # RIGHT = identity of who's certifying them (signature + credentials)
    # This is the standard diploma convention, and it's what actually
    # balances the page — both sides now carry comparable visual weight.
    #
    # Vertical zones (measured, not guessed) so nothing here can ever
    # collide with the decorative wave again: the wave's true peak was
    # numerically verified at y≈48. Everything below y=90 is off-limits
    # to any footer content; the disclaimer strip (y=50-78) is reserved
    # and untouchable by anything added above it in the future.
    # =========================================================
    footer_top = 210      # top of the photo/signature row
    footer_bottom = 95    # bottom of the photo/signature row (>90 clearance kept)

    cx_left = inner + 20 + 45     # rough visual center of the left column
    cx_right = width - inner - 20 - 85   # rough visual center of the right column

    # ---- LEFT: trainee photo with the hospital seal straddling its edge ----
    photo_w, photo_h = 90, 110
    photo_x = inner + 20
    photo_y = footer_bottom + 5

    if trainee_photo:
        try:
            trainee_img = ImageReader(f"static/uploads/photos/{trainee_photo}")
            c.drawImage(trainee_img, photo_x, photo_y, width=photo_w, height=photo_h,
                        preserveAspectRatio=True, mask='auto')
        except Exception as e:
            print("Photo Error:", e)

        try:
            seal = ImageReader(seal_path)
            c.drawImage(seal, photo_x + photo_w - 32, photo_y - 8, width=64, height=64, mask='auto')
        except Exception as e:
            print("Seal Error:", e)
    else:
        # No trainee photo on file (blank template / quick certificate) —
        # show the seal alone, centered in the same column, instead of
        # leaving an empty gap or a seal awkwardly straddling nothing.
        try:
            seal = ImageReader(seal_path)
            seal_size = 72
            c.drawImage(seal, cx_left - seal_size / 2, photo_y + (photo_h - seal_size) / 2,
                        width=seal_size, height=seal_size, mask='auto')
        except Exception as e:
            print("Seal Error:", e)

    # ---- RIGHT: signature line + doctor's credentials, centered ----
    sig_x1 = width - inner - 190
    sig_x2 = width - inner - 20
    sig_cx = (sig_x1 + sig_x2) / 2
    sig_y = footer_top - 10

    c.setStrokeColorRGB(*INK)
    c.setLineWidth(0.7)
    c.line(sig_x1, sig_y, sig_x2, sig_y)

    c.setFillColorRGB(*NAVY_DARK)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawCentredString(sig_cx, sig_y - 15, doctor_name)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawCentredString(sig_cx, sig_y - 27, doctor_cred)
    c.setFont("Helvetica", 8)
    for i, line in enumerate(address_lines):
        c.drawCentredString(sig_cx, sig_y - 40 - i * 11, line)

    # ---- Reserved disclaimer strip — permanently clear of the wave ----
    if cert_no:
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.setFont("Helvetica", 7.5)
        c.drawString(inner + 14, 78, f"Cert. No: {cert_no}")

    c.setStrokeColorRGB(*GOLD)
    c.setLineWidth(0.7)
    c.line(inner + 20, 68, width - inner - 20, 68)
    c.setFillColorRGB(*NAVY_DARK)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawCentredString(cx, 56,
                         "This certificate is system-generated by Amrutha Aarogya Kendra Ayurvedic Hospital.")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
