import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'realbrothers2024secretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///realbrothers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/profiles'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB Limit

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)

# Constants
GROUP_START_YEAR = 2023
MONTHLY_CONTRIBUTION = 200
LATE_FEE = 50
ABSENT_FEE = 200
ANNUAL_DOWRY = 15000

# --- MODELS ---

class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='member') # admin, member
    status = db.Column(db.String(20), default='active') # active, dormant, suspended, exited
    is_special = db.Column(db.Boolean, default=False)
    phone = db.Column(db.String(20))
    profile_pic = db.Column(db.String(255), default='default_profile.png')
    joined_year = db.Column(db.Integer, default=GROUP_START_YEAR)
    joined_date = db.Column(db.DateTime, default=datetime.utcnow)
    dowry_received = db.Column(db.Integer, default=0)
    dowry_queue_position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    payments = db.relationship('Payment', backref='member', lazy=True, cascade="all, delete-orphan")
    fds = db.relationship('FixedDeposit', backref='member', lazy=True)
    refunds = db.relationship('MemberRefund', backref='member', lazy=True)
    attendances = db.relationship('Attendance', backref='member', lazy=True)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    payment_type = db.Column(db.String(50), nullable=False) # monthly, apology, dowry, fine
    amount = db.Column(db.Float, nullable=False)
    month = db.Column(db.Integer)
    year = db.Column(db.Integer)
    notes = db.Column(db.String(200))
    recorded_by = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False) # Income, Expense, Refund
    category = db.Column(db.String(50)) # monthly, dowry_payout, interest, etc.
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    reference_id = db.Column(db.Integer) # ID of the specific record (Payment ID, Expense ID, etc.)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False) # Dowry Payout, Admin, Bank Fee, Meeting
    amount = db.Column(db.Float, nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id')) # If payout to member
    description = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class FixedDeposit(db.Model):
    __tablename__ = 'fixed_deposits'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'))
    principal_amount = db.Column(db.Float, nullable=False)
    interest_earned = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Active') # Active, Matured
    start_date = db.Column(db.DateTime, default=datetime.utcnow)

class MemberRefund(db.Model):
    __tablename__ = 'member_refunds'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow().date())
    status = db.Column(db.String(20)) # Present, Absent, Late
    fine_amount = db.Column(db.Float, default=0.0)

# --- HELPERS ---

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def get_financial_summary():
    total_income = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.type == 'Income').scalar() or 0
    total_expenses = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.type == 'Expense').scalar() or 0
    total_refunds = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.type == 'Refund').scalar() or 0
    
    current_balance = total_income - total_expenses - total_refunds
    
    income_breakdown = db.session.query(Transaction.category, db.func.sum(Transaction.amount)).filter(Transaction.type == 'Income').group_by(Transaction.category).all()
    expense_breakdown = db.session.query(Transaction.category, db.func.sum(Transaction.amount)).filter(Transaction.type == 'Expense').group_by(Transaction.category).all()
    
    return {
        'total_income': total_income,
        'total_expenses': total_expenses,
        'total_refunds': total_refunds,
        'current_balance': current_balance,
        'income_breakdown': dict(income_breakdown),
        'expense_breakdown': dict(expense_breakdown)
    }

def get_member_stats(member_id, year=None):
    if not year: year = datetime.now().year
    m = Member.query.get(member_id)
    now = datetime.now()
    
    # Financial Totals
    paid = db.session.query(db.func.sum(Payment.amount)).filter_by(member_id=member_id).scalar() or 0
    refunded = db.session.query(db.func.sum(MemberRefund.amount)).filter_by(member_id=member_id).scalar() or 0
    
    # Yearly Breakdowns
    yearly_data = {}
    chart_labels = []
    chart_values = []
    
    for y in range(2023, 2031):
        y_total = db.session.query(db.func.sum(Payment.amount)).filter_by(member_id=member_id, year=y).scalar() or 0
        
        # Get paid months for this year
        paid_months = [p.month for p in Payment.query.filter_by(member_id=member_id, payment_type='monthly', year=y).all()]
        
        yearly_data[y] = {
            'total': y_total, 
            'monthly_count': len(paid_months),
            'paid_months': paid_months
        }
        if y <= now.year:
            chart_labels.append(str(y))
            chart_values.append(y_total)

    # --- DOWRY ELIGIBILITY LOGIC ---
    flags = []
    is_eligible = True
    
    # 1. Monthly Pattern (Lateness)
    monthly_payments = Payment.query.filter_by(member_id=member_id, payment_type='monthly', year=now.year).all()
    for p in monthly_payments:
        if p.created_at.month > p.month: 
            is_eligible = False
            flags.append(f"Late Payment for Month {p.month} (Paid {p.created_at.strftime('%b %d')})")

    # 2. Dowry Deadlines (7500 by June, 15000 by Dec)
    dowry_payments = Payment.query.filter_by(member_id=member_id, payment_type='dowry', year=now.year).all()
    june_total = sum(p.amount for p in dowry_payments if p.created_at.month <= 6)
    dec_total = sum(p.amount for p in dowry_payments)
    
    if now.month > 6 and june_total < 7500:
        is_eligible = False
        flags.append("Missed June Dowry Goal (KES 7,500)")
    if now.month == 12 and dec_total < 15000:
        is_eligible = False
        flags.append("Missed Dec Dowry Goal (KES 15,000)")

    # 3. Attendance (Consistency check)
    if not m.is_special:
        absences = Attendance.query.filter_by(member_id=member_id, status='Absent').count()
        if absences > 0:
            is_eligible = False
            flags.append("Attendance is not common")

    # 4. Long-term Lateness (> 4 months)
    start_y = m.joined_year or GROUP_START_YEAR
    total_expected = (now.year - start_y) * 12 + now.month
    total_paid_months = Payment.query.filter_by(member_id=member_id, payment_type='monthly').count()
    if (total_expected - total_paid_months) > 4:
        is_eligible = False
        flags.append("Arrears exceed 4 months")

    total_fines = db.session.query(db.func.sum(Payment.amount)).filter_by(member_id=member_id, payment_type='fine').scalar() or 0
    
    return {
        'total_paid': paid,
        'total_refunded': refunded,
        'net_position': paid - refunded,
        'yearly_data': yearly_data,
        'status': m.status,
        'total_fines': total_fines,
        'is_eligible': is_eligible,
        'flags': flags,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'is_special': m.is_special
    }

# --- ROUTES ---

@app.route('/')
def index():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Member.query.filter_by(username=request.form['username'].strip()).first()
        if user and check_password_hash(user.password, request.form['password']):
            session.update({'user_id': user.id, 'name': user.name, 'role': user.role})
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    fins = get_financial_summary()
    members_list = Member.query.filter(Member.status != 'exited').all()
    next_dowry = Member.query.filter_by(dowry_received=0, status='active').order_by(Member.dowry_queue_position).first()
    
    user_stats = get_member_stats(session['user_id']) if session['role'] == 'member' else None
    
    return render_template('dashboard.html', fins=fins, member_count=len(members_list), 
                           next_dowry=next_dowry, user_stats=user_stats, year=datetime.now().year,
                           MONTHLY_CONTRIBUTION=MONTHLY_CONTRIBUTION, ANNUAL_DOWRY=ANNUAL_DOWRY)

@app.route('/admin/financials')
@admin_required
def reports():
    fins = get_financial_summary()
    transactions = Transaction.query.order_by(Transaction.timestamp.desc()).limit(50).all()
    return render_template('financials.html', fins=fins, transactions=transactions)

@app.route('/admin/record-expense', methods=['GET', 'POST'])
@admin_required
def record_expense():
    members = Member.query.filter_by(status='active').all()
    if request.method == 'POST':
        category = request.form['category']
        amount = float(request.form['amount'])
        mid = request.form.get('member_id')
        desc = request.form.get('description', '')
        
        exp = Expense(category=category, amount=amount, member_id=mid, description=desc)
        db.session.add(exp)
        db.session.flush()
        
        t = Transaction(type='Expense', category=category, amount=amount, description=desc, reference_id=exp.id)
        db.session.add(t)
        
        if category == 'Dowry Payout' and mid:
            m = Member.query.get(mid)
            m.dowry_received = 1
            
        db.session.commit()
        flash('Expense recorded successfully')
        return redirect(url_for('reports'))
    return render_template('record_expense.html', members=members)

@app.route('/admin/record-interest', methods=['GET', 'POST'])
@admin_required
def record_interest():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        desc = request.form.get('description', 'FD Interest Earned')
        
        t = Transaction(type='Income', category='Interest', amount=amount, description=desc)
        db.session.add(t)
        db.session.commit()
        flash('Interest income recorded')
        return redirect(url_for('reports'))
    return render_template('record_interest.html')

@app.route('/admin/process-refund', methods=['GET', 'POST'])
@admin_required
def process_refund():
    members = Member.query.filter(Member.status != 'exited').all()
    if request.method == 'POST':
        mid = request.form['member_id']
        amount = float(request.form['amount'])
        reason = request.form.get('reason', 'Member Exit')
        was_dowry_paid = request.form.get('was_dowry_paid') == 'yes'
        
        ref = MemberRefund(member_id=mid, amount=amount, reason=reason)
        db.session.add(ref)
        db.session.flush()
        
        # Record Transaction as 'Refund' - our helper get_financial_summary already deducts this
        t = Transaction(
            type='Refund', 
            category='Member Refund', 
            amount=amount, 
            description=f"Refund to {mid} (Dowry Paid: {was_dowry_paid}): {reason}", 
            reference_id=ref.id
        )
        db.session.add(t)
        
        m = Member.query.get(mid)
        m.status = 'exited'
        if was_dowry_paid:
            m.dowry_received = 1
        
        db.session.commit()
        flash(f'Refund of KES {amount:,.0f} processed. Member status updated to Left.', 'success')
        return redirect(url_for('reports'))
    return render_template('process_refund.html', members=members)

# Keep existing record-payment and manage-members routes with Transaction logic
@app.route('/admin/record-payment', methods=['GET', 'POST'])
@admin_required
def record_payment():
    members = Member.query.filter(Member.status != 'exited').all()
    if request.method == 'POST':
        mid = request.form['member_id']
        ptype = request.form['payment_type']
        amt = float(request.form.get('amount', 200))
        year = int(request.form.get('year', datetime.now().year))
        month = request.form.get('month')
        pdate_str = request.form.get('payment_date')
        
        # Parse custom date or use now
        pdate = datetime.strptime(pdate_str, '%Y-%m-%d') if pdate_str else datetime.utcnow()
        
        p = Payment(member_id=mid, payment_type=ptype, amount=amt, month=month, year=year, 
                    recorded_by=session['user_id'], created_at=pdate)
        db.session.add(p)
        db.session.flush()
        
        t = Transaction(type='Income', category=ptype, amount=amt, 
                        description=f"{ptype} from member {mid}", reference_id=p.id, timestamp=pdate)
        db.session.add(t)
        db.session.commit()
        flash('Payment recorded successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('record_payment.html', members=members, year=datetime.now().year, ANNUAL_DOWRY=ANNUAL_DOWRY)

@app.route('/admin/members', methods=['GET', 'POST'])
@admin_required
def manage_members():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form['name'].strip()
            uname = request.form['username'].strip().lower()
            joined_year = int(request.form.get('joined_year', GROUP_START_YEAR))
            status = request.form.get('status', 'active')
            
            if Member.query.filter_by(username=uname).first():
                flash(f'Error: Username "{uname}" is already taken.', 'error')
            else:
                max_pos = db.session.query(db.func.max(Member.dowry_queue_position)).scalar() or 0
                new_m = Member(
                    name=name, 
                    username=uname, 
                    password=generate_password_hash(request.form.get('password', 'brothers2024')),
                    joined_year=joined_year,
                    status=status,
                    dowry_queue_position=max_pos + 1
                )
                db.session.add(new_m)
                db.session.commit()
                flash(f'Member {name} added successfully', 'success')
        
        elif action == 'dowry_received':
            mid = request.form.get('member_id')
            m = Member.query.get(mid)
            if m:
                m.dowry_received = 1
                # Record it as an expense for accounting
                exp = Expense(category='Dowry Payout', amount=ANNUAL_DOWRY, member_id=mid, description=f"Automatic payout marking for {m.name}")
                db.session.add(exp)
                db.session.flush()
                t = Transaction(type='Expense', category='Dowry Payout', amount=ANNUAL_DOWRY, description=f"Dowry payout to {m.name}", reference_id=exp.id)
                db.session.add(t)
                db.session.commit()
                flash(f'Dowry support marked for {m.name}', 'success')

        elif action == 'delete':
            mid = request.form.get('member_id')
            m = Member.query.get(mid)
            if m:
                db.session.delete(m)
                db.session.commit()
                flash('Member deleted successfully', 'success')
                
        elif action == 'status':
            m = Member.query.get(request.form['member_id'])
            if m:
                m.status = request.form['status']
                db.session.commit()
                flash('Status updated', 'success')
        
        elif action == 'edit_name':
            mid = request.form.get('member_id')
            new_name = request.form.get('name').strip()
            m = Member.query.get(mid)
            if m and new_name:
                old_name = m.name
                m.name = new_name
                db.session.commit()
                flash(f'Member name updated from "{old_name}" to "{new_name}"', 'success')
        
        elif action == 'toggle_special':
            mid = request.form.get('member_id')
            m = Member.query.get(mid)
            if m:
                m.is_special = not m.is_special
                db.session.commit()
                flash(f'Special status updated for {m.name}', 'success')
    
    members = Member.query.order_by(Member.name).all()
    return render_template('manage_members.html', members=members)

@app.route('/member/<int:member_id>')
@login_required
def member_detail(member_id):
    if session['role'] == 'member' and session['user_id'] != member_id: return redirect(url_for('dashboard'))
    m = Member.query.get_or_404(member_id)
    payments = Payment.query.filter_by(member_id=member_id).order_by(Payment.created_at.desc()).all()
    stats = get_member_stats(member_id)
    return render_template('member.html', member=m, payments=payments, stats=stats, year=datetime.now().year, ANNUAL_DOWRY=ANNUAL_DOWRY)

@app.route('/upload-profile', methods=['POST'])
@login_required
def upload_profile():
    if 'profile_pic' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('member_detail', member_id=session['user_id']))
    
    file = request.files['profile_pic']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('member_detail', member_id=session['user_id']))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"user_{session['user_id']}_{file.filename}")
        upload_path = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
        os.makedirs(upload_path, exist_ok=True)
        file.save(os.path.join(upload_path, filename))
        
        member = Member.query.get(session['user_id'])
        member.profile_pic = filename
        db.session.commit()
        
        flash('Profile picture updated!', 'success')
    else:
        flash('Invalid file type. Use PNG, JPG, or GIF.', 'error')
        
    return redirect(url_for('member_detail', member_id=session['user_id']))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Member.query.filter_by(username='admin').first():
            admin = Member(name='Admin', username='admin', password=generate_password_hash('admin123'), role='admin')
            db.session.add(admin)
            db.session.commit()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
