from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='member') # super_admin, admin, member
    status = db.Column(db.String(20), default='active') # active, dormant, suspended, exited
    is_special = db.Column(db.Boolean, default=False)
    phone = db.Column(db.String(20))
    profile_pic = db.Column(db.String(255), default='default_profile.png')
    joined_year = db.Column(db.Integer, default=2023)
    joined_date = db.Column(db.DateTime, default=datetime.utcnow)
    dowry_received = db.Column(db.Integer, default=0)
    dowry_queue_position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Security fields from RBAC Guide
    failed_login_attempts = db.Column(db.Integer, default=0)
    account_locked = db.Column(db.Boolean, default=False)
    locked_until = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    last_password_change = db.Column(db.DateTime)

    # Relationships
    payments = db.relationship('Payment', backref='member', lazy=True, cascade="all, delete-orphan")
    fds = db.relationship('FixedDeposit', backref='member', lazy=True)
    refunds = db.relationship('MemberRefund', backref='member', lazy=True)
    attendances = db.relationship('Attendance', backref='member', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def has_permission(self, permission):
        from role_permissions import has_feature
        return has_feature(self.role, permission)

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

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'))
    action = db.Column(db.String(100))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LoginHistory(db.Model):
    __tablename__ = 'login_history'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'))
    username = db.Column(db.String(50))
    success = db.Column(db.Boolean)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    reason = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
