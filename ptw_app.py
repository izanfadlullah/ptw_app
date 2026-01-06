import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
import os
import tempfile
from fpdf import FPDF

# --- CONFIGURATION & SETUP ---
st.set_page_config(page_title="Digital Permit to Work", page_icon="👷", layout="wide")

# --- SECURITY SETTINGS ---
# 🔒 CHANGE THIS CODE TO WHATEVER YOU WANT
ADMIN_ACCESS_CODE = "KISWIRE2026" 

# --- DATABASE FUNCTIONS ---
def init_db():
    conn = sqlite3.connect('ptw_database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS permits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contractor_name TEXT,
            work_type TEXT,
            location TEXT,
            description TEXT,
            status TEXT,
            request_date TIMESTAMP,
            approval_date TIMESTAMP,
            approver_name TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permit_id INTEGER,
            stage TEXT,
            image_data BLOB,
            timestamp TIMESTAMP,
            FOREIGN KEY(permit_id) REFERENCES permits(id)
        )
    ''')
    conn.commit()
    conn.close()

def submit_permit(name, w_type, loc, desc):
    conn = sqlite3.connect('ptw_database.db')
    c = conn.cursor()
    c.execute('INSERT INTO permits (contractor_name, work_type, location, description, status, request_date) VALUES (?, ?, ?, ?, ?, ?)',
              (name, w_type, loc, desc, 'Pending Review', datetime.now()))
    permit_id = c.lastrowid
    conn.commit()
    conn.close()
    return permit_id

def upload_photo(permit_id, stage, image_file):
    if image_file is not None:
        conn = sqlite3.connect('ptw_database.db')
        c = conn.cursor()
        img_bytes = image_file.read()
        c.execute('INSERT INTO photos (permit_id, stage, image_data, timestamp) VALUES (?, ?, ?, ?)',
                  (permit_id, stage, img_bytes, datetime.now()))
        conn.commit()
        conn.close()

def get_permits():
    conn = sqlite3.connect('ptw_database.db')
    df = pd.read_sql_query("SELECT * FROM permits", conn)
    conn.close()
    return df

def update_status(permit_id, new_status, approver=None):
    conn = sqlite3.connect('ptw_database.db')
    c = conn.cursor()
    if approver:
        c.execute('UPDATE permits SET status = ?, approval_date = ?, approver_name = ? WHERE id = ?',
                  (new_status, datetime.now(), approver, permit_id))
    else:
        c.execute('UPDATE permits SET status = ? WHERE id = ?', (new_status, permit_id))
    conn.commit()
    conn.close()

def get_photos(permit_id):
    conn = sqlite3.connect('ptw_database.db')
    c = conn.cursor()
    c.execute('SELECT stage, image_data, timestamp FROM photos WHERE permit_id = ?', (permit_id,))
    data = c.fetchall()
    conn.close()
    return data

# --- PDF GENERATION FUNCTION ---
def create_pdf(permit_id):
    conn = sqlite3.connect('ptw_database.db')
    # Check if permit exists
    try:
        row = pd.read_sql_query(f"SELECT * FROM permits WHERE id={permit_id}", conn).iloc[0]
    except IndexError:
        conn.close()
        return None

    photos = get_photos(permit_id)
    conn.close()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Permit to Work Report - #{permit_id}", ln=True, align='C')
    pdf.ln(10)

    # Details
    pdf.set_font("Arial", size=10)
    details = [
        ("Contractor Name", row['contractor_name']),
        ("Work Type", row['work_type']),
        ("Location", row['location']),
        ("Status", row['status']),
        ("Requested Date", str(row['request_date'])),
        ("Approved By", str(row['approver_name']) if row['approver_name'] else "N/A"),
        ("Description", row['description'])
    ]

    for key, value in details:
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(50, 10, txt=key + ":", border=1)
        pdf.set_font("Arial", size=10)
        pdf.cell(140, 10, txt=str(value), border=1, ln=True)
    
    pdf.ln(10)
    
    # Photos
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Site Photos & Evidence", ln=True)
    pdf.ln(5)

    if photos:
        for stage, img_data, ts in photos:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                tmp_file.write(img_data)
                tmp_path = tmp_file.name
            
            pdf.set_font("Arial", 'B', 11)
            pdf.cell(200, 10, txt=f"Stage: {stage} (Taken: {ts})", ln=True)
            try:
                pdf.image(tmp_path, w=100)
            except:
                pdf.cell(200, 10, txt="[Error loading image]", ln=True)
            pdf.ln(10)
            os.unlink(tmp_path)
    else:
        pdf.cell(200, 10, txt="No photos attached.", ln=True)

    return pdf.output(dest='S').encode('latin-1')

# --- INITIALIZE DB ---
init_db()

# --- SIDEBAR & AUTHENTICATION ---
st.sidebar.title("🔐 Login Portal")
role = st.sidebar.radio("Select Your Role:", ["Contractor", "Safety Officer (SHO)", "Project Manager (PIC)"])
st.sidebar.markdown("---")

# Auth Logic
access_granted = False

if role == "Contractor":
    # Contractors do not need a password
    access_granted = True
else:
    # Admin roles need password
    st.sidebar.warning(f"🔒 {role} Area Protected")
    password_input = st.sidebar.text_input("Enter Access Code:", type="password")
    
    if password_input == ADMIN_ACCESS_CODE:
        access_granted = True
        st.sidebar.success("Access Granted ✅")
    elif password_input:
        st.sidebar.error("Wrong Access Code ❌")

# --- MAIN APP LOGIC ---

if not access_granted:
    # Show Lock Screen
    st.title("🔒 Access Denied")
    st.info("Please enter the correct Access Code in the sidebar to view the Dashboard.")
    st.stop() # Stop the script here if not authenticated

# If we pass here, access is granted
if role == "Contractor":
    st.title("👷 Contractor Portal")
    st.info("Fill in the form below to apply for a permit or update an active job.")
    
    tab1, tab2 = st.tabs(["🆕 New Application", "📸 Update Active Work"])
    
    with tab1:
        with st.form("ptw_form"):
            c_name = st.text_input("Contractor Name")
            w_type = st.selectbox("Type of Work", ["Hot Work", "Height", "Confined Space", "Electrical", "Lifting"])
            loc = st.text_input("Location")
            desc = st.text_area("Description")
            st.markdown("**Initial Photo (Before Work)**")
            photo_before = st.file_uploader("Upload Image", type=['jpg', 'png'], key="p_before")
            
            if st.form_submit_button("Submit"):
                if c_name and loc and photo_before:
                    pid = submit_permit(c_name, w_type, loc, desc)
                    upload_photo(pid, "Before", photo_before)
                    st.success(f"Permit #{pid} submitted!")
                else:
                    st.error("Fill all fields and upload photo.")

    with tab2:
        df = get_permits()
        active = df[df['status'].isin(['Approved', 'Work In Progress'])]
        if not active.empty:
            p_select = st.selectbox("Select Permit", active['id'].astype(str) + " - " + active['location'])
            pid = int(p_select.split(" - ")[0])
            
            c1, c2 = st.columns(2)
            with c1:
                p_during = st.file_uploader("During Work Photo", key="u_during")
                if st.button("Upload 'During'"):
                    upload_photo(pid, "During", p_during)
                    st.success("Uploaded!")
            with c2:
                p_after = st.file_uploader("After Work Photo", key="u_after")
                if st.button("Upload 'After' & Finish"):
                    upload_photo(pid, "After", p_after)
                    update_status(pid, "Work Done (Pending Close)")
                    st.success("Sent for closing.")
        else:
            st.warning("No active permits found.")

else:
    # ADMIN VIEW (SHO / PIC)
    st.title(f"🛡️ {role} Dashboard")
    
    tab_rev, tab_db = st.tabs(["📝 Reviews", "📊 Database & Reports"])
    
    with tab_rev:
        st.subheader("Action Required")
        df = get_permits()
        pending = df[df['status'].isin(['Pending Review', 'Work Done (Pending Close)'])]
        
        if pending.empty:
            st.success("No pending tasks. Good job! 👍")
        
        for _, row in pending.iterrows():
            with st.expander(f"#{row['id']} | {row['contractor_name']} | {row['status']}"):
                st.write(f"**Desc:** {row['description']}")
                cols = st.columns(3)
                photos = get_photos(row['id'])
                for i, (stage, img, ts) in enumerate(photos):
                    cols[i%3].image(img, caption=stage, use_container_width=True)
                
                if row['status'] == 'Pending Review':
                    if st.button("Approve", key=f"a_{row['id']}"):
                        update_status(row['id'], "Approved", role)
                        st.rerun()
                elif row['status'] == 'Work Done (Pending Close)':
                    if st.button("Verify & Close", key=f"c_{row['id']}"):
                        update_status(row['id'], "Closed", role)
                        st.rerun()

    with tab_db:
        st.subheader("Master Record")
        df = get_permits()
        st.dataframe(df)
        
        st.divider()
        st.write("### 📄 Generate PDF Report")
        p_id_report = st.number_input("Enter Permit ID for Report:", min_value=1, step=1)
        
        # PDF Download
        pdf_bytes = create_pdf(p_id_report)
        if pdf_bytes:
            st.download_button(
                label="📥 Download PDF Report",
                data=pdf_bytes,
                file_name=f"Permit_Report_{p_id_report}.pdf",
                mime="application/pdf"
            )
        elif p_id_report > 0:
            st.warning("Permit ID not found.")