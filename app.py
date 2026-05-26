import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from functools import wraps
from werkzeug.security import generate_password_hash

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
ANNUAL_CONTRIBUTION = Config.ANNUAL_CONTRIBUTION
SUPPORT_PAYOUT = Config.SUPPORT_PAYOUT

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
    
    paid = db.session.query(db.func.sum(Payment.amount)).filter_by(member_id=member_id).scalar() or 0
    refunded = db.session.query(db.func.sum(MemberRefund.amount)).filter_by(member_id=member_id).scalar() or 0
    
    yearly_data = {}
    chart_labels = []
    chart_values = []
    
    for y in range(2023, 2031):
        y_total = db.session.query(db.func.sum(Payment.amount)).filter_by(member_id=member_id, year=y).scalar() or 0
        paid_months = [p.month for p in Payment.query.filter_by(member_id=member_id, payment_type='monthly', year=y).all()]
        yearly_data[y] = {'total': y_total, 'monthly_count': len(paid_months), 'paid_months': paid_months}
        if y <= now.year:
            chart_labels.append(str(y))
            chart_values.append(y_total)

    flags = []
    is_eligible = True
    
    monthly_payments = Payment.query.filter_by(member_id=member_id, payment_type='monthly', year=now.year).all()
    for p in monthly_payments:
        if p.created_at.month > p.month: 
            is_eligible = False
            flags.append(f"Late Payment for Month {p.month} (Paid {p.created_at.strftime('%b %d')})")

    contribution_payments = Payment.query.filter_by(member_id=member_id, payment_type='dowry', year=now.year).all()
    june_total = sum(p.amount for p in contribution_payments if p.created_at.month <= 6)
    dec_total = sum(p.amount for p in contribution_payments)
    
    if now.month > 6 and june_total < (ANNUAL_CONTRIBUTION / 2):
        is_eligible = False
        flags.append(f"Missed June Contribution Goal (KES {ANNUAL_CONTRIBUTION / 2:,.0f})")
    if now.month == 12 and dec_total < ANNUAL_CONTRIBUTION:
        is_eligible = False
        flags.append(f"Missed Dec Contribution Goal (KES {ANNUAL_CONTRIBUTION:,.0f})")

    if not m.is_special:
        absences = Attendance.query.filter_by(member_id=member_id, status='Absent').count()
        if absences > 0:
            is_eligible = False
            flags.append("Attendance issue")

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
        'is_special': m.is_special,
        'monthly_paid': len([p for p in monthly_payments if p.year == now.year])
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
            from rbac import check_account_locked, increment_failed_attempts, reset_failed_attempts
            is_locked, message = check_account_locked(user)
            if is_locked:
                flash(message, 'error')
                return render_template('login.html')
            if user.check_password(password):
                reset_failed_attempts(user)
                session.update({'user_id': user.id, 'name': user.name, 'role': user.role})
                history = LoginHistory(member_id=user.id, username=username, success=True, 
                                       ip_address=request.remote_addr, user_agent=request.user_agent.string)
                db.session.add(history)
                db.session.commit()
                return redirect(url_for('dashboard'))
            else:
                is_locked, message = increment_failed_attempts(user)
                flash('Invalid credentials. ' + message, 'error')
                history = LoginHistory(member_id=user.id, username=username, success=False, 
                                       ip_address=request.remote_addr, user_agent=request.user_agent.string,
                                       reason='Invalid Password')
                db.session.add(history)
                db.session.commit()
        else:
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
    next_support = Member.query.filter_by(dowry_received=0, status='active').order_by(Member.dowry_queue_position).first()
    user_stats = get_member_stats(session['user_id'])
    return render_template('dashboard.html', fins=fins, member_count=len(members_list), 
                           next_support=next_support, user_stats=user_stats, year=datetime.now().year,
                           MONTHLY_CONTRIBUTION=MONTHLY_CONTRIBUTION, ANNUAL_CONTRIBUTION=ANNUAL_CONTRIBUTION)

@app.route('/admin/financials')
@admin_required
def financials():
    fins = get_financial_summary()
    transactions = Transaction.query.order_by(Transaction.timestamp.desc()).limit(100).all()
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
        if category == 'Member Support' and mid:
            Member.query.get(mid).dowry_received = 1
        db.session.commit()
        flash('Expense recorded successfully')
        return redirect(url_for('financials'))
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
        return redirect(url_for('financials'))
    return render_template('record_interest.html')

@app.route('/admin/process-refund', methods=['GET', 'POST'])
@admin_required
def process_refund():
    members = Member.query.filter(Member.status != 'exited').all()
    if request.method == 'POST':
        mid = request.form['member_id']
        amount = float(request.form['amount'])
        reason = request.form.get('reason', 'Member Exit')
        was_support_paid = request.form.get('was_support_paid') == 'yes'
        ref = MemberRefund(member_id=mid, amount=amount, reason=reason)
        db.session.add(ref)
        db.session.flush()
        t = Transaction(type='Refund', category='Member Refund', amount=amount, 
                        description=f"Refund to {mid} (Support Paid: {was_support_paid}): {reason}", reference_id=ref.id)
        db.session.add(t)
        m = Member.query.get(mid)
        m.status = 'exited'
        if was_support_paid:
            m.dowry_received = 1
        db.session.commit()
        flash(f'Refund processed', 'success')
        return redirect(url_for('financials'))
    return render_template('process_refund.html', members=members)

@app.route('/admin/attendance', methods=['GET', 'POST'])
@admin_required
def attendance():
    members = Member.query.filter(Member.status != 'exited').order_by(Member.name).all()
    today = datetime.now().date()
    if request.method == 'POST':
        meeting_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        Attendance.query.filter_by(date=meeting_date).delete()
        for m in members:
            status = request.form.get(f'status_{m.id}', 'Absent')
            fine = float(request.form.get(f'fine_{m.id}', 0))
            db.session.add(Attendance(member_id=m.id, date=meeting_date, status=status, fine_amount=fine))
            if fine > 0:
                p = Payment(member_id=m.id, payment_type='fine', amount=fine, notes=f"Fine for {status} on {meeting_date}", recorded_by=session['user_id'])
                db.session.add(p)
                db.session.flush()
                db.session.add(Transaction(type='Income', category='fine', amount=fine, description=f"Fine: {status} on {meeting_date}", reference_id=p.id))
        db.session.commit()
        flash('Attendance recorded')
        return redirect(url_for('dashboard'))
    return render_template('attendance.html', members=members, today=today)

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
        pdate = datetime.strptime(pdate_str, '%Y-%m-%d') if pdate_str else datetime.utcnow()
        p = Payment(member_id=mid, payment_type=ptype, amount=amt, month=month, year=year, recorded_by=session['user_id'], created_at=pdate)
        db.session.add(p)
        db.session.flush()
        db.session.add(Transaction(type='Income', category=ptype, amount=amt, description=f"{ptype} payment", reference_id=p.id, timestamp=pdate))
        db.session.commit()
        flash('Payment recorded')
        return redirect(url_for('dashboard'))
    return render_template('record_payment.html', members=members, year=datetime.now().year, ANNUAL_CONTRIBUTION=ANNUAL_CONTRIBUTION)

import csv
import io
from flask import make_response

@app.route('/admin/export-report')
@admin_required
def export_report():
    year = request.args.get('year', datetime.now().year, type=int)
    members = Member.query.filter(Member.status != 'exited').order_by(Member.name).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Member Name', 'Monthly Paid', 'Months Expected', 'Months Missed', 'Dowry Paid', 'Dowry Remaining', 'Apology Savings', 'Total Paid'])
    
    now = datetime.now()
    months_to_date = now.month if year == now.year else 12
    if year < now.year: months_to_date = 12

    for m in members:
        if m.joined_year > year: continue
        
        m_months_expected = months_to_date
        monthly_paid = Payment.query.filter_by(member_id=m.id, payment_type='monthly', year=year).count()
        months_missed = max(0, m_months_expected - monthly_paid)
        
        dowry_paid = db.session.query(db.func.sum(Payment.amount)).filter_by(member_id=m.id, payment_type='dowry', year=year).scalar() or 0
        dowry_remaining = max(0, ANNUAL_CONTRIBUTION - dowry_paid)
        
        apology_total = db.session.query(db.func.sum(Payment.amount)).filter_by(member_id=m.id, payment_type='apology', year=year).scalar() or 0
        total_member_paid = monthly_paid * MONTHLY_CONTRIBUTION + dowry_paid + apology_total
        
        writer.writerow([m.name, monthly_paid, m_months_expected, months_missed, dowry_paid, dowry_remaining, apology_total, total_member_paid])
    
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=real_brothers_report_{year}.csv"
    response.headers["Content-type"] = "text/csv"
    return response

@app.route('/admin/members', methods=['GET', 'POST'])
@admin_required
def manage_members():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            uname = request.form['username'].strip().lower()
            role = request.form.get('role', 'member')
            if role in ['admin', 'super_admin'] and session['role'] != 'super_admin':
                flash('Only Super Admin can create admins', 'error')
            elif Member.query.filter_by(username=uname).first():
                flash('Username taken', 'error')
            else:
                max_pos = db.session.query(db.func.max(Member.dowry_queue_position)).scalar() or 0
                new_m = Member(name=request.form['name'].strip(), username=uname, role=role,
                               joined_year=int(request.form.get('joined_year', GROUP_START_YEAR)), 
                               status=request.form.get('status', 'active'), 
                               dowry_queue_position=max_pos + 1)
                new_m.set_password(request.form.get('password', 'brothers2024'))
                db.session.add(new_m)
                db.session.commit()
                log_action(session['user_id'], 'Add Member', f'Added member {uname}')
                flash('Member added')
        
        elif action == 'edit_name':
            mid = request.form.get('member_id')
            m = Member.query.get(mid)
            if m:
                old_name = m.name
                m.name = request.form.get('name')
                db.session.commit()
                log_action(session['user_id'], 'Edit Member Name', f'Changed {old_name} to {m.name}')
                flash('Name updated')
        
        elif action == 'status':
            mid = request.form.get('member_id')
            new_status = request.form.get('status')
            m = Member.query.get(mid)
            if m:
                m.status = new_status
                db.session.commit()
                log_action(session['user_id'], 'Update Status', f'Changed {m.username} status to {new_status}')
                flash(f'Status updated to {new_status}')
        
        elif action == 'toggle_special':
            mid = request.form.get('member_id')
            m = Member.query.get(mid)
            if m:
                m.is_special = not m.is_special
                db.session.commit()
                status_str = "Special" if m.is_special else "Normal"
                log_action(session['user_id'], 'Toggle Special', f'Changed {m.username} to {status_str}')
                flash(f'Member marked as {status_str}')

        elif action == 'dowry_received':
            mid = request.form.get('member_id')
            m = Member.query.get(mid)
            if m:
                m.dowry_received = 1
                db.session.commit()
                log_action(session['user_id'], 'Mark Dowry Received', f'Marked dowry received for {m.username}')
                flash('Member marked as dowry received')

    members = Member.query.order_by(Member.name).all()
    return render_template('manage_members.html', members=members)

@app.route('/admin/manage-admins', methods=['GET', 'POST'])
@super_admin_required
def manage_admins():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            uname = request.form['username'].strip().lower()
            if Member.query.filter_by(username=uname).first():
                flash('Username taken', 'error')
            else:
                new_admin = Member(name=request.form['name'].strip(), username=uname, role=request.form.get('role', 'admin'))
                new_admin.set_password(request.form.get('password', 'admin123'))
                db.session.add(new_admin)
                db.session.commit()
                log_action(session['user_id'], 'Create Admin', f'Created admin {uname}')
                flash('Admin created')
        elif action == 'delete':
            mid = request.form.get('member_id')
            if int(mid) == session['user_id']:
                flash('Cannot delete yourself', 'error')
            else:
                m = Member.query.get(mid)
                if m:
                    uname = m.username
                    db.session.delete(m)
                    db.session.commit()
                    log_action(session['user_id'], 'Delete Admin', f'Deleted admin {uname}')
                    flash('Admin account deleted')
    admins = Member.query.filter(Member.role.in_(['admin', 'super_admin'])).all()
    return render_template('manage_admins.html', admins=admins)

@app.route('/admin/audit-logs')
@super_admin_required
def audit_logs():
    return render_template('audit_logs.html', logs=AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all())

@app.route('/admin/login-history')
@super_admin_required
def login_history():
    return render_template('login_history.html', history=LoginHistory.query.order_by(LoginHistory.timestamp.desc()).limit(100).all())

@app.route('/admin/settings', methods=['GET', 'POST'])
@super_admin_required
def settings():
    return render_template('settings.html')

@app.route('/admin/reports')
@admin_required
def reports():
    year = request.args.get('year', datetime.now().year, type=int)
    members = Member.query.filter(Member.status != 'exited').order_by(Member.name).all()
    
    report_data = []
    total_expected_monthly = 0
    total_expected_dowry = 0
    
    now = datetime.now()
    months_to_date = now.month if year == now.year else 12
    if year < now.year: months_to_date = 12
    if year > now.year: months_to_date = 0

    for m in members:
        if m.joined_year > year: continue
        
        m_months_expected = months_to_date
        monthly_payments = Payment.query.filter_by(member_id=m.id, payment_type='monthly', year=year).all()
        monthly_paid = len(monthly_payments)
        months_missed = max(0, m_months_expected - monthly_paid)
        
        dowry_payments = Payment.query.filter_by(member_id=m.id, payment_type='dowry', year=year).all()
        dowry_paid = sum(p.amount for p in dowry_payments)
        dowry_remaining = max(0, ANNUAL_CONTRIBUTION - dowry_paid)
        
        apology_payments = Payment.query.filter_by(member_id=m.id, payment_type='apology', year=year).all()
        apology_total = sum(p.amount for p in apology_payments)
        
        total_member_paid = monthly_paid * MONTHLY_CONTRIBUTION + dowry_paid + apology_total
        
        report_data.append({
            'id': m.id,
            'name': m.name,
            'monthly_paid': monthly_paid,
            'months_expected': m_months_expected,
            'months_missed': months_missed,
            'dowry_paid': dowry_paid,
            'dowry_remaining': dowry_remaining,
            'apology_total': apology_total,
            'total_paid': total_member_paid
        })
        
        total_expected_monthly += m_months_expected * MONTHLY_CONTRIBUTION
        total_expected_dowry += ANNUAL_CONTRIBUTION

    months_grid = []
    for month in range(1, 13):
        paid_count = Payment.query.filter_by(payment_type='monthly', year=year, month=month).count()
        expected_this_month = Member.query.filter(Member.joined_year <= year, Member.status != 'exited').count()
        months_grid.append({
            'month': month,
            'paid': paid_count,
            'missed': max(0, expected_this_month - paid_count) if month <= months_to_date else 0
        })

    return render_template('reports.html', report=report_data, year=year, 
                           total_expected_monthly=total_expected_monthly,
                           total_expected_dowry=total_expected_dowry,
                           months_data=months_grid)

@app.route('/upload-profile', methods=['POST'])
@login_required
def upload_profile():
    if 'profile_pic' not in request.files:
        flash('No file part')
        return redirect(request.referrer)
    file = request.files['profile_pic']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.referrer)
    if file and allowed_file(file.filename):
        filename = secure_filename(f"user_{session['user_id']}_{file.filename}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file.save(file_path)
        m = Member.query.get(session['user_id'])
        m.profile_pic = filename
        db.session.commit()
        flash('Profile picture updated')
    return redirect(request.referrer)

@app.route('/member/<int:member_id>')
@login_required
def member_detail(member_id):
    if session['role'] == 'member' and session['user_id'] != member_id: return redirect(url_for('dashboard'))
    m = Member.query.get_or_404(member_id)
    payments = Payment.query.filter_by(member_id=member_id).order_by(Payment.created_at.desc()).all()
    return render_template('member.html', member=m, payments=payments, stats=get_member_stats(member_id), year=datetime.now().year, ANNUAL_CONTRIBUTION=ANNUAL_CONTRIBUTION)

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password')
        new_pw = request.form.get('new_password')
        confirm_pw = request.form.get('confirm_password')
        
        user = Member.query.get(session['user_id'])
        if not user.check_password(current_pw):
            flash('Current password incorrect', 'error')
        elif new_pw != confirm_pw:
            flash('Passwords do not match', 'error')
        elif len(new_pw) < 4:
            flash('Password too short', 'error')
        else:
            user.set_password(new_pw)
            user.last_password_change = datetime.utcnow()
            db.session.commit()
            log_action(user.id, 'Change Password')
            flash('Password changed successfully', 'success')
            return redirect(url_for('dashboard'))
            
    return render_template('change_password.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error_code=404, message="Page Not Found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_code=500, message="Internal Server Error"), 500

# Initialize database and default users
with app.app_context():
    db.create_all()
    james = Member.query.filter_by(username='james').first()
    if not james:
        james = Member(name='James Kithome', username='james', role='super_admin')
        james.set_password('13456')
        db.session.add(james)
        db.session.commit()
        print("James Kithome account verified.")

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
