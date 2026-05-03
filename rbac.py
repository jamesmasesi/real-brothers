"""
Comprehensive RBAC (Role-Based Access Control) Implementation
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, render_template
from models import Member, db
from datetime import datetime, timedelta

# ============================================================================
# DECORATORS FOR ACCESS CONTROL
# ============================================================================

def login_required(f):
    """Require user to be logged in"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('login'))
        
        # Check if user still exists
        user = Member.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('User account no longer exists.', 'error')
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    """Require Super Admin role"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('login'))
        
        user = Member.query.get(session['user_id'])
        if not user or user.role != 'super_admin':
            flash('👑 Super Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Require Admin or Super Admin role"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('login'))
        
        user = Member.query.get(session['user_id'])
        if not user or user.role not in ['admin', 'super_admin']:
            flash('🔧 Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Require one of specified roles"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in first.', 'error')
                return redirect(url_for('login'))
            
            user = Member.query.get(session['user_id'])
            if not user or user.role not in roles:
                role_names = ', '.join(roles)
                flash(f'Access denied. Required role: {role_names}', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated
    return decorator


def permission_required(permission):
    """Require specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in first.', 'error')
                return redirect(url_for('login'))
            
            user = Member.query.get(session['user_id'])
            if not user or not user.has_permission(permission):
                flash(f'Permission denied: {permission}', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated
    return decorator


# ============================================================================
# AUTHORIZATION CHECK FUNCTIONS
# ============================================================================

def can_view_user(current_user, target_user):
    """Check if current user can view target user"""
    if current_user.id == target_user.id:
        return True
    
    if current_user.role == 'super_admin':
        return True
    
    if current_user.role == 'admin' and target_user.role == 'member':
        return True
    
    return False


def can_edit_user(current_user, target_user):
    """Check if current user can edit target user"""
    if current_user.role == 'super_admin':
        return True
    
    if current_user.role == 'admin' and target_user.role == 'member':
        return True
    
    # Users can edit their own profile
    if current_user.id == target_user.id:
        return True
    
    return False


def can_delete_user(current_user, target_user):
    """Check if current user can delete target user"""
    if current_user.role != 'super_admin':
        return False
    
    # Cannot delete self
    if current_user.id == target_user.id:
        return False
    
    return True


def can_create_admin(current_user):
    """Check if current user can create admin accounts"""
    return current_user.role == 'super_admin'


def can_manage_admin(current_user, target_admin):
    """Check if current user can manage an admin account"""
    if current_user.role != 'super_admin':
        return False
    
    if current_user.id == target_admin.id:
        return False  # Cannot manage self
    
    return True


def can_record_payment(current_user):
    """Check if current user can record payments"""
    return current_user.role in ['admin', 'super_admin']


def can_view_reports(current_user):
    """Check if current user can view financial reports"""
    return current_user.role in ['admin', 'super_admin']


def can_view_audit_logs(current_user):
    """Check if current user can view audit logs"""
    return current_user.role == 'super_admin'


# ============================================================================
# ACCOUNT SECURITY FUNCTIONS
# ============================================================================

def check_account_locked(user):
    """Check if account is locked due to failed login attempts"""
    if user.account_locked:
        if user.locked_until and datetime.utcnow() < user.locked_until:
            remaining = (user.locked_until - datetime.utcnow()).total_seconds() / 60
            return True, f"Account locked. Try again in {int(remaining)} minutes."
        else:
            # Unlock account
            user.account_locked = False
            user.locked_until = None
            user.failed_login_attempts = 0
            db.session.commit()
            return False, ""
    return False, ""


def increment_failed_attempts(user, lock_attempts=5, lock_duration=30):
    """Increment failed login attempts and lock if necessary"""
    user.failed_login_attempts += 1
    
    if user.failed_login_attempts >= lock_attempts:
        user.account_locked = True
        user.locked_until = datetime.utcnow() + timedelta(minutes=lock_duration)
        db.session.commit()
        return True, f"Account locked for {lock_duration} minutes after {lock_attempts} failed attempts."
    
    db.session.commit()
    remaining = lock_attempts - user.failed_login_attempts
    return False, f"Attempt {user.failed_login_attempts}/{lock_attempts}. {remaining} attempts remaining."


def reset_failed_attempts(user):
    """Reset failed login attempts after successful login"""
    user.failed_login_attempts = 0
    user.account_locked = False
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.session.commit()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_role_display(role):
    """Get human-readable role name with emoji"""
    role_map = {
        'super_admin': '👑 Super Admin',
        'admin': '🔧 Admin',
        'member': '👤 Member'
    }
    return role_map.get(role, role)


def get_role_badge_html(role):
    """Get HTML badge for role"""
    badge_map = {
        'super_admin': '<span class="badge badge-danger">👑 Super Admin</span>',
        'admin': '<span class="badge badge-warning">🔧 Admin</span>',
        'member': '<span class="badge badge-info">👤 Member</span>'
    }
    return badge_map.get(role, f'<span class="badge badge-secondary">{role}</span>')


def get_user_context(user):
    """Get context data for user (role, permissions, etc.)"""
    return {
        'role': user.role,
        'role_display': get_role_display(user.role),
        'is_super_admin': user.role == 'super_admin',
        'is_admin': user.role in ['admin', 'super_admin'],
        'is_member': user.role == 'member',
        'can_manage_admins': user.role == 'super_admin',
        'can_manage_members': user.role in ['admin', 'super_admin'],
        'can_record_payments': user.role in ['admin', 'super_admin'],
        'can_view_reports': user.role in ['admin', 'super_admin'],
        'can_view_audit_logs': user.role == 'super_admin',
    }
