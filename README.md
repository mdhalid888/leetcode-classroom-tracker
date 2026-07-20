# LeetCode Classroom Tracker

An elegant, automated platform designed for educational institutions, placement cells, and coding clubs to track, analyze, and gamify students' LeetCode progress in real-time.

---

## 🚀 Key Features

* **Real-time Leaderboard**: Automatically ranks students based on total problems solved, with secondary rankings for Easy, Medium, Hard solves, Streaks, and **Today's Solves**.
* **On-Demand Dynamic Sync**: Automatically triggers a profile scraper fetch when a student loads or refreshes any main page if their profile data is more than 2 minutes stale.
* **Daily Classroom Tasks**: Admins can assign multiple LeetCode problems daily. Assigned tasks appear as a dynamic ordered checklist on the student dashboard and automatically reset at midnight IST.
* **Secure Admin Controls**: Protected workspace login using tab-bound `sessionStorage` authentication, allowing admins to manage student rosters, assign/delete daily tasks, and run database scanners.
* **Format-Free Exporting**: One-click Excel spreadsheet and print-friendly PDF report generation for the entire classroom roster without requesting login credentials.
* **Visual Performance Badges**: High-contrast, clean status pills indicating student difficulty breakdowns (Easy, Medium, Hard solves) and active solving streaks.

---

## 🛠 Tech Stack

* **Backend API**: Python, Flask, Flask-SQLAlchemy (PostgreSQL / Supabase integration).
* **Frontend Dashboard**: Vanilla HTML5, CSS3, JavaScript, Bootstrap 5 (Responsive glassmorphism styling).
* **Scraper Core**: LeetCode GraphQL API wrapper with asynchronous HTTP requests and automated timezone handling (IST alignment).

---

## 💻 Local Setup & Development

### 1. Prerequisites
Ensure you have Python 3.10+ installed.

### 2. Clone the Repository
```bash
git clone https://github.com/mdhalid888/leetcode-classroom-tracker.git
cd leetcode-classroom-tracker
```

### 3. Create a Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Set Environment Variables
Create a `.env` file in the root directory (or set them in your terminal session):
```env
DATABASE_URL=postgresql://username:password@host:port/database
PORT=5000
```

### 6. Run the Database Seeder (Optional)
If initializing the database for the first time:
```bash
python seed_db.py
```

### 7. Start the Server
```bash
python app.py
```
The application will run locally at `http://127.0.0.1:5000`.

---

## 🌐 Production Deployment

* **Backend API Hosting**: Render (using WSGI server).
* **Frontend Static Hosting**: Vercel (routing dynamic calls to the Render API endpoint via `vercel.json` rewrite paths).
