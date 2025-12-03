import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURATION (Yahan apni details dalein) ---
APP_ID = "752530667096904"
APP_SECRET = "b6d8ff4dfb303c20c52acea26527eeab"
FB_API_URL = "https://graph.facebook.com/v18.0"

# --- PAGE SETUP ---
st.set_page_config(page_title="FB Scheduler", page_icon="📅")
st.title("📘 Facebook Bulk Scheduler")

# --- SESSION STATE (Login yaad rakhne ke liye) ---
if 'access_token' not in st.session_state:
    st.session_state['access_token'] = None

# --- HELPER FUNCTIONS ---
def get_long_lived_token(short_token):
    url = f"{FB_API_URL}/oauth/access_token"
    params = {
        'grant_type': 'fb_exchange_token',
        'client_id': APP_ID,
        'client_secret': APP_SECRET,
        'fb_exchange_token': short_token
    }
    r = requests.get(url, params=params)
    return r.json().get('access_token')

def get_pages(token):
    url = f"{FB_API_URL}/me/accounts"
    params = {'access_token': token}
    r = requests.get(url, params=params)
    return r.json().get('data', [])

# --- MAIN LOGIC ---

# 1. Agar user Login nahi hai
if not st.session_state['access_token']:
    
    # Check karein ke kya Facebook wapas aaya hai (URL mein Code hai?)
    query_params = st.query_params
    auth_code = query_params.get("code")

    if auth_code:
        # Code mil gaya! Token exchange karein
        # Hamein pata nahi URL kya hai, isliye current URL automatic detect karenge (Localhost workaround)
        # Note: Deploy hone ke baad user ko URL set karna padega
        redirect_uri = "https://share.streamlit.io" # Temporary placeholder
        
        # Lekin Streamlit Cloud par URL alag hota hai.
        # Behtar tareeqa: Hum user se Login karwayenge.
        pass 
    
    st.markdown("### Step 1: Login")
    
    # Streamlit Cloud URL Strategy
    # Hum user ko bolenge ke pehle Deploy kare, phir URL yahan copy kare
    
    redirect_uri = st.text_input("Apne App ka Link yahan paste karein (Jaisa: https://myapp.streamlit.app)", value="http://localhost:8501")
    st.caption("Pehle is app ko deploy karein, phir uska link yahan dalein aur Facebook Developer Settings mein bhi wahi link dalein.")
    
    if st.button("Login with Facebook"):
        if APP_ID == "YAHAN_APNA_APP_ID_PASTE_KAREIN":
             st.error("Please code mein APP_ID aur SECRET update karein!")
        else:
            oauth_url = f"https://www.facebook.com/v18.0/dialog/oauth?client_id={APP_ID}&redirect_uri={redirect_uri}&scope=pages_show_list,pages_manage_posts,pages_read_engagement"
            st.link_button("👉 Click here to Login", oauth_url)

    # Agar Facebook wapas code bhejta hai
    if auth_code:
        with st.spinner("Logging in..."):
            # Token Exchange
            token_url = f"{FB_API_URL}/oauth/access_token"
            r_params = {
                'client_id': APP_ID,
                'redirect_uri': redirect_uri, # Must match exactly what was entered
                'client_secret': APP_SECRET,
                'code': auth_code
            }
            resp = requests.get(token_url, params=r_params).json()
            
            if 'access_token' in resp:
                long_token = get_long_lived_token(resp['access_token'])
                st.session_state['access_token'] = long_token
                # URL saaf karein
                st.query_params.clear()
                st.rerun()
            else:
                st.error(f"Login Failed: {resp}")

# 2. Agar user Login hai (Dashboard)
else:
    token = st.session_state['access_token']
    st.success("✅ You are Logged In!")
    
    if st.button("Logout"):
        st.session_state['access_token'] = None
        st.rerun()
    
    st.divider()
    
    # Pages fetch karein
    pages = get_pages(token)
    
    if not pages:
        st.warning("Koi Facebook Page nahi mila.")
    else:
        st.subheader("1. Select Pages")
        page_options = {p['name']: p for p in pages}
        selected_page_names = st.multiselect("Kin Pages par post karni hai?", list(page_options.keys()))
        
        st.subheader("2. Upload CSV")
        st.info("CSV Columns: message, image_url, scheduled_time (YYYY-MM-DD HH:MM:SS)")
        uploaded_file = st.file_uploader("Choose CSV", type=['csv'])
        
        if uploaded_file and selected_page_names:
            if st.button("🚀 Schedule Posts"):
                df = pd.read_csv(uploaded_file)
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_posts = len(selected_page_names) * len(df)
                processed = 0
                
                for page_name in selected_page_names:
                    page_data = page_options[page_name]
                    page_access_token = page_data['access_token']
                    page_id = page_data['id']
                    
                    for index, row in df.iterrows():
                        msg = row['message']
                        img_url = row.get('image_url', None)
                        time_str = row['scheduled_time']
                        
                        # Time Conversion
                        try:
                            dt_obj = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                            unix_time = int(time.mktime(dt_obj.timetuple()))
                            
                            payload = {
                                'message': msg,
                                'published': 'false',
                                'scheduled_publish_time': unix_time,
                                'access_token': page_access_token
                            }
                            
                            endpoint = f"{FB_API_URL}/{page_id}/feed"
                            if img_url and str(img_url) != 'nan':
                                payload['url'] = img_url
                                endpoint = f"{FB_API_URL}/{page_id}/photos"
                                
                            r = requests.post(endpoint, data=payload)
                            
                        except Exception as e:
                            st.error(f"Error: {e}")
                        
                        processed += 1
                        progress_bar.progress(processed / total_posts)
                
                status_text.success("All posts processed!")
                st.balloons()
