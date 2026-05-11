import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from functools import wraps

from config import Config
from models import db, Member, Payment, Transaction, Expense, FixedDeposit, MemberRefund, Attendance, AuditLog, LoginHistory
from rbac import login_required, admin_required, super_admin_required, role_required

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
migrate = Migrate(app, db)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Constants from Config
GROUP_START_YEAR = Config.GROUP_START_YEAR
MONTHLY_CONTRIBUTION = Config.MONTHLY_CONTRIBUTION
LATE_FEE = Config.LATE_FEE
ABSENT_FEE = Config.ABSENT_FEE
ANNUAL_DOWRY = Config.ANNUAL_DOWRY

# Helper for Audit Logging
def log_action(member_id, action, details=None):
    log = AuditLog(
        member_id=member_id,
        action=action,
        details=details,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(log)
    db.session.commit()

# --- HELPERS ---

# (get_financial_summary and get_member_stats remain here as they are app-specific logic)

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
        username = request.form['username'].strip()
        password = request.form['password']
        user = Member.query.filter_by(username=username).first()
        
        if user:
            # Check lockout
            from rbac import check_account_locked, increment_failed_attempts, reset_failed_attempts
            is_locked, message = check_account_locked(user)
            if is_locked:
                flash(message, 'error')
                return render_template('login.html')
            
            if user.check_password(password):
                reset_failed_attempts(user)
                session.update({'user_id': user.id, 'name': user.name, 'role': user.role})
                
                # Log login
                history = LoginHistory(member_id=user.id, username=username, success=True, 
                                       ip_address=request.remote_addr, user_agent=request.user_agent.string)
                db.session.add(history)
                db.session.commit()
                
                return redirect(url_for('dashboard'))
            else:
                is_locked, message = increment_failed_attempts(user)
                flash('Invalid credentials. ' + message, 'error')
                
                # Log failed login
                history = LoginHistory(member_id=user.id, username=username, success=False, 
                                       ip_address=request.remote_addr, user_agent=request.user_agent.string,
                                       reason='Invalid Password')
                db.session.add(history)
                db.session.commit()
        else:
            flash('Invalid credentials')
            # Log unknown user login attempt
            history = LoginHistory(username=username, success=False, 
                                   ip_address=request.remote_addr, user_agent=request.user_agent.string,
                                   reason='User Not Found')
            db.session.add(history)
            db.session.commit()
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_action(session['user_id'], 'Logout')
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

@app.route('/admin/manage-admins', methods=['GET', 'POST'])
@super_admin_required
def manage_admins():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form['name'].strip()
            uname = request.form['username'].strip().lower()
            role = request.form.get('role', 'admin')
            
            if Member.query.filter_by(username=uname).first():
                flash(f'Error: Username "{uname}" is already taken.', 'error')
            else:
                new_admin = Member(name=name, username=uname, role=role)
                new_admin.set_password(request.form.get('password', 'admin123'))
                db.session.add(new_admin)
                db.session.commit()
                log_action(session['user_id'], f'Created Admin: {uname}', f'Role: {role}')
                flash(f'Admin {name} created successfully', 'success')
        
        elif action == 'delete':
            mid = request.form.get('member_id')
            if int(mid) == session['user_id']:
                flash('You cannot delete yourself!', 'error')
            else:
                m = Member.query.get(mid)
                if m:
                    uname = m.username
                    db.session.delete(m)
                    db.session.commit()
                    log_action(session['user_id'], f'Deleted Admin: {uname}')
                    flash('Admin deleted successfully', 'success')

    admins = Member.query.filter(Member.role.in_(['admin', 'super_admin'])).all()
    return render_template('manage_admins.html', admins=admins)

@app.route('/admin/audit-logs')
@super_admin_required
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('audit_logs.html', logs=logs)

@app.route('/admin/login-history')
@super_admin_required
def login_history():
    history = LoginHistory.query.order_by(LoginHistory.timestamp.desc()).limit(100).all()
    return render_template('login_history.html', history=history)

@app.route('/admin/settings', methods=['GET', 'POST'])
@super_admin_required
def settings():
    if request.method == 'POST':
        # Handle group settings updates here if needed
        flash('Settings updated (simulated)', 'success')
    return render_template('settings.html')

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
        # Create default super_admin if it doesn't exist
        if not Member.query.filter_by(role='super_admin').first():
            super_admin = Member(name='Super Admin', username='admin', role='super_admin')
            super_admin.set_password('admin123')
            db.session.add(super_admin)
            db.session.commit()
            print("Default super_admin created: admin / admin123")
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
