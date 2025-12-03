import os
from flask import Flask, render_template, request, redirect, session, url_for
import requests
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
from datetime import datetime
import time

app = Flask(__muffer__)
app.secret_key = 'random_secret_key_kuch_bhi_likh_do'

# --- CONFIGURATION (YAHAN APNI DETAILS DALEIN) ---
APP_ID = "752530667096904"
APP_SECRET = "b6d8ff4dfb303c20c52acea26527eeab"
# Note: Jab Render par jayenge toh URL change hoga, isliye dynamic rakha hai.
FB_API_URL = "https://graph.facebook.com/v18.0"

# --- DATABASE SETUP ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///scheduler.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fb_user_id = db.Column(db.String(50), unique=True)
    access_token = db.Column(db.String(255))
    pages = db.relationship('Page', backref='owner', lazy=True)

class Page(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page_name = db.Column(db.String(100))
    page_id = db.Column(db.String(50))
    page_token = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# App start hone par database banao
with app.app_context():
    db.create_all()

# --- ROUTES ---

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/login')
def login():
    # Render ka URL automatic uthane ke liye
    redirect_uri = url_for('callback', _external=True, _scheme='https')
    return redirect(
        f"https://www.facebook.com/v18.0/dialog/oauth?client_id={APP_ID}&redirect_uri={redirect_uri}&scope=pages_show_list,pages_manage_posts,pages_read_engagement"
    )

@app.route('/callback')
def callback():
    code = request.args.get('code')
    redirect_uri = url_for('callback', _external=True, _scheme='https')
    
    # 1. Exchange Code for Token
    token_url = f"{FB_API_URL}/oauth/access_token?client_id={APP_ID}&redirect_uri={redirect_uri}&client_secret={APP_SECRET}&code={code}"
    resp = requests.get(token_url).json()
    
    if 'access_token' not in resp:
        return f"Error logging in: {resp}"
    
    short_token = resp['access_token']
    
    # 2. Get Long Lived Token
    long_token_url = f"{FB_API_URL}/oauth/access_token?grant_type=fb_exchange_token&client_id={APP_ID}&client_secret={APP_SECRET}&fb_exchange_token={short_token}"
    long_resp = requests.get(long_token_url).json()
    access_token = long_resp.get('access_token', short_token)
    
    # 3. Get User Info
    user_info = requests.get(f"{FB_API_URL}/me?access_token={access_token}").json()
    fb_user_id = user_info['id']
    
    # 4. Save User to DB
    user = User.query.filter_by(fb_user_id=fb_user_id).first()
    if not user:
        user = User(fb_user_id=fb_user_id, access_token=access_token)
        db.session.add(user)
    else:
        user.access_token = access_token
    db.session.commit()
    
    session['user_id'] = user.id
    
    # 5. Fetch Pages
    pages_resp = requests.get(f"{FB_API_URL}/me/accounts?access_token={access_token}").json()
    
    # Purane pages hata kar naye save karein (Refresh)
    Page.query.filter_by(user_id=user.id).delete()
    
    for page_data in pages_resp.get('data', []):
        new_page = Page(
            page_name=page_data['name'],
            page_id=page_data['id'],
            page_token=page_data['access_token'],
            owner=user
        )
        db.session.add(new_page)
    db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    user = db.session.get(User, session['user_id'])
    pages = user.pages
    status_msg = ""
    
    if request.method == 'POST':
        # File Handling
        if 'csv_file' not in request.files:
            return "No file part"
        file = request.files['csv_file']
        selected_pages = request.form.getlist('pages')
        
        if file.filename == '':
            return "No selected file"
        
        if file:
            try:
                # CSV Read karo
                df = pd.read_csv(file)
                
                success_count = 0
                
                for page_id in selected_pages:
                    # Database se page token nikalo
                    target_page = Page.query.filter_by(page_id=page_id).first()
                    
                    if target_page:
                        for index, row in df.iterrows():
                            msg = row['message']
                            img_url = row.get('image_url', None) # Optional
                            time_str = row['scheduled_time'] # Format: 2023-12-30 15:00:00
                            
                            # Time Convert to UNIX Timestamp
                            dt_obj = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                            unix_time = int(time.mktime(dt_obj.timetuple()))
                            
                            # API Parameters
                            payload = {
                                'message': msg,
                                'published': 'false',
                                'scheduled_publish_time': unix_time,
                                'access_token': target_page.page_token
                            }
                            if img_url and str(img_url) != 'nan':
                                payload['url'] = img_url
                                endpoint = f"{FB_API_URL}/{page_id}/photos"
                            else:
                                endpoint = f"{FB_API_URL}/{page_id}/feed"
                            
                            # Send Request
                            r = requests.post(endpoint, data=payload)
                            if r.status_code == 200:
                                success_count += 1
                            else:
                                print(f"Error: {r.text}")
                                
                status_msg = f"Successfully Scheduled {success_count} posts!"
                
            except Exception as e:
                status_msg = f"Error: {str(e)}"

    return render_template('dashboard.html', pages=pages, msg=status_msg)

if __name__ == '__main__':
    app.run(debug=True)