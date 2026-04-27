# Real Brothers Savings Group App

## Quick Start (Windows)

### Step 1: Install Python
1. Go to https://python.org/downloads
2. Download the latest Python (3.11 or newer)
3. Run the installer — **check the box "Add Python to PATH"**
4. Click Install

### Step 2: Set Up the App
1. Extract the `real_brothers` folder anywhere (e.g., your Desktop)
2. Double-click `START.bat`
3. Wait for it to install Flask (first time only)
4. A browser should open automatically to http://localhost:5000

### Step 3: First Login
- **Admin username:** `admin`
- **Admin password:** `admin123`
- **Change this password immediately!** Go to Manage Members → find admin → Reset PW

---

## Adding Your 24 Members

1. Log in as admin
2. Go to **Members** in the top navigation
3. Click **Add New Member** for each person
4. Fill in: Full Name, Username (no spaces), Phone (optional)
5. Default password is `brothers2024` — members can ask you to change it

**Example members to add:**
- Name: James Mwangi, Username: jamesm
- Name: Peter Kamau, Username: peterk
- etc.

---

## Daily Admin Tasks

### Recording Monthly Payment
1. Click **Record** in the navigation
2. Select member name
3. Select **Monthly Contribution** (KES 200)
4. Select the month being paid
5. Click Record Payment

### Recording Apology Saving
1. Click **Record**
2. Select member
3. Select **Apology Saving** (KES 200)
4. Notes: write what the apology was for
5. Click Record Payment

### Recording Annual Dowry Contribution
1. Click **Record**
2. Select member
3. Select **Annual Dowry Contribution**
4. Amount defaults to 15,000 (change if partial payment)
5. Click Record Payment

### Marking a Member as Dowry Received
1. Go to **Members** admin page
2. Find the member
3. Click the 💍 button → confirm

---

## Sharing With Group Members

### Option A: Local Network (Easiest)
When you run the app, it listens on `0.0.0.0:5000`.
Members on the same WiFi can access it at:
`http://YOUR-COMPUTER-IP:5000`

To find your IP:
1. Press Win+R, type `cmd`, press Enter
2. Type `ipconfig`
3. Look for "IPv4 Address" (e.g., 192.168.1.5)
4. Share: `http://192.168.1.5:5000`

**Note:** Your computer must be on and the app running.

### Option B: Free Cloud Hosting (Permanent URL)
Deploy to Railway.app (free tier works for 24 members):
1. Create account at https://railway.app
2. Install Railway CLI or use GitHub
3. Upload the `real_brothers` folder
4. Get a permanent URL like `https://real-brothers.railway.app`

### Option C: ngrok (Quick Public Access)
1. Download ngrok from https://ngrok.com
2. Run your app: `python app.py`
3. In another terminal: `ngrok http 5000`
4. Share the https URL ngrok gives you

---

## Member Accounts

Each member gets:
- **Username:** set by admin (e.g., "johnk")
- **Password:** set by admin (default: brothers2024)
- **Access:** Read-only view of group dashboard + their own detailed account

Members CAN:
- View the group dashboard (totals, who's next for dowry)
- View their own payment history and status
- See the monthly payment tracker calendar

Members CANNOT:
- Record payments (admin only)
- See other members' details beyond the summary table
- Add/remove members

---

## Database

The app uses SQLite — all data is stored in `realbrothers.db` in the app folder.
**Back this file up regularly!** Copy it to Google Drive or email it to yourself weekly.

---

## Changing the Admin Password
1. Log in as admin
2. Go to Members
3. Find "Admin" at the bottom of the list
4. Click "Reset PW" and enter a new password

---

## Troubleshooting

**"python is not recognized"**: Python not in PATH. Reinstall Python and check "Add to PATH".

**Port already in use**: Change `port=5000` to `port=5001` in `app.py` line near the bottom.

**Members can't access from phone**: Make sure they're on the same WiFi. Check Windows Firewall allows port 5000.

**Lost admin password**: Delete `realbrothers.db` to reset everything (warning: loses all data) or use SQLite Browser to manually update.
