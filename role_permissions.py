"""
ROLE-BASED DASHBOARD CONFIGURATION
Controls what each role can see and do
"""

ROLE_PERMISSIONS = {
    'super_admin': {
        'emoji': '👑',
        'name': 'Super Admin',
        'dashboard_cards': ['overview', 'users', 'admins', 'members', 'financials', 'activity'],
        'menu_items': [
            {'label': 'Dashboard', 'icon': '📊', 'url': 'dashboard'},
            {'label': 'Manage Admins', 'icon': '🔧', 'url': 'manage_admins'},
            {'label': 'Manage Members', 'icon': '👥', 'url': 'manage_members'},
            {'label': 'Record Payment', 'icon': '💰', 'url': 'record_payment'},
            {'label': 'Financial Reports', 'icon': '📈', 'url': 'reports'},
            {'label': 'Audit Logs', 'icon': '🔍', 'url': 'audit_logs'},
            {'label': 'Settings', 'icon': '⚙️', 'url': 'settings'},
        ],
        'features': [
            'create_admin',
            'edit_admin',
            'delete_admin',
            'manage_members',
            'view_reports',
            'record_payments',
            'view_audit_logs',
            'system_settings'
        ]
    },
    'admin': {
        'emoji': '🔧',
        'name': 'Admin',
        'dashboard_cards': ['overview', 'members', 'financials'],
        'menu_items': [
            {'label': 'Dashboard', 'icon': '📊', 'url': 'dashboard'},
            {'label': 'Members', 'icon': '👥', 'url': 'manage_members'},
            {'label': 'Record Payment', 'icon': '💰', 'url': 'record_payment'},
            {'label': 'Financial Reports', 'icon': '📈', 'url': 'reports'},
        ],
        'features': [
            'manage_members',
            'record_payments',
            'view_reports',
            'process_refunds'
        ]
    },
    'member': {
        'emoji': '👤',
        'name': 'Member',
        'dashboard_cards': ['my_account', 'group_overview'],
        'menu_items': [
            {'label': 'Dashboard', 'icon': '📊', 'url': 'dashboard'},
            {'label': 'My Account', 'icon': '👤', 'url': 'member_detail', 'params': {'member_id': 'user_id'}},
        ],
        'features': [
            'view_profile',
            'view_payments',
            'upload_profile_pic'
        ]
    }
}

def get_role_info(role):
    """Get role information"""
    return ROLE_PERMISSIONS.get(role, {})

def get_menu_items(role):
    """Get menu items for role"""
    return get_role_info(role).get('menu_items', [])

def has_feature(role, feature):
    """Check if role has specific feature"""
    features = get_role_info(role).get('features', [])
    return feature in features

def get_dashboard_cards(role):
    """Get dashboard cards for role"""
    return get_role_info(role).get('dashboard_cards', [])
