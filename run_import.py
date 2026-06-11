import pandas as pd
import re
from app import app, db, Member, Payment, Transaction
from datetime import datetime

file_path = r'C:\Users\hp\.gemini\tmp\system32\real-brothers\2026-REALBROTHERS 11 MAY 2026.xlsx'

def normalize_name(name):
    if pd.isna(name): return ""
    return re.sub(r'\s+', ' ', str(name).strip()).upper()

MONTH_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 
    'JULY': 7, 'AUG/ONES ': 8, 'SEP/PAUL': 9, 'OCT': 10, 'NOV': 11
}

with app.app_context():
    df = pd.read_excel(file_path)
    
    # Get all members for mapping
    members = Member.query.all()
    name_to_id = {normalize_name(m.name): m.id for m in members}
    
    recorded_count = 0
    skipped_count = 0
    
    for _, row in df.iterrows():
        excel_name = normalize_name(row['MEMBER'])
        if not excel_name or excel_name == 'TOTALS':
            continue
            
        member_id = name_to_id.get(excel_name)
        if not member_id:
            print(f"Warning: Member '{row['MEMBER']}' not found in database.")
            continue
            
        # Process Monthly Payments
        for col, month_num in MONTH_MAP.items():
            amount = row.get(col)
            if pd.notna(amount) and amount > 0:
                # Check if exists
                existing = Payment.query.filter_by(
                    member_id=member_id, 
                    payment_type='monthly', 
                    month=month_num, 
                    year=2026
                ).first()
                
                if not existing:
                    p = Payment(
                        member_id=member_id,
                        payment_type='monthly',
                        amount=float(amount),
                        month=month_num,
                        year=2026,
                        recorded_by=1, # Admin
                        notes=f"Imported from Excel ({col})",
                        created_at=datetime(2026, month_num, 1)
                    )
                    db.session.add(p)
                    db.session.flush()
                    
                    t = Transaction(
                        type='Income',
                        category='monthly',
                        amount=float(amount),
                        description=f"Monthly payment {col} 2026",
                        reference_id=p.id,
                        timestamp=datetime(2026, month_num, 1)
                    )
                    db.session.add(t)
                    recorded_count += 1
                else:
                    skipped_count += 1
                    
        # Process Wave 1 & 2 (Dowry)
        for col in ['WAVE 1 ', 'WAVE 2']:
            amount = row.get(col)
            if pd.notna(amount) and amount > 0:
                # For dowry, we might have multiple payments per year, so check by notes/amount
                existing = Payment.query.filter_by(
                    member_id=member_id,
                    payment_type='dowry',
                    year=2026,
                    notes=f"Imported from Excel ({col.strip()})"
                ).first()
                
                if not existing:
                    p = Payment(
                        member_id=member_id,
                        payment_type='dowry',
                        amount=float(amount),
                        year=2026,
                        recorded_by=1,
                        notes=f"Imported from Excel ({col.strip()})",
                        created_at=datetime(2026, 1, 1) # Arbitrary date for 2026
                    )
                    db.session.add(p)
                    db.session.flush()
                    
                    t = Transaction(
                        type='Income',
                        category='dowry',
                        amount=float(amount),
                        description=f"Dowry payment {col.strip()} 2026",
                        reference_id=p.id,
                        timestamp=datetime(2026, 1, 1)
                    )
                    db.session.add(t)
                    recorded_count += 1
                else:
                    skipped_count += 1
                    
    db.session.commit()
    print(f"\nImport finished!")
    print(f"Recorded: {recorded_count} new payments")
    print(f"Skipped: {skipped_count} existing payments")
