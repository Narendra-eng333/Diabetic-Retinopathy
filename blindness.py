# blindness.py
# Final updated file with:
# - PDF Layout A (Name, Gender, <blank>, Age, Contact)
# - Generated logo/image usage (falls back to creating simple images)
# - Signup font size increased and centered vertically
# - Pages expand to full window
# - Patient table has grid/alternating rows
# - Diagnosis label + class saved, history maintained
# - Auto-ALTER DB (diagnosis, diagnosis_class, history) at startup

import os
import sys
import traceback
import datetime
import webbrowser
import inspect

import mysql.connector as sk
from tkinter import *
from tkinter import ttk, messagebox
from tkinter.filedialog import askopenfilename
from PIL import Image, ImageTk, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT

# import your model (expects main)
import model



# ----------------------------
# Database connection
# ----------------------------
try:
    connection = sk.connect(
        host="localhost",
        user="root",
        password="root@123",
        database="DR_Database"
    )
    sql = connection.cursor()
    DB_OK = True
except Exception as e:
    print("[WARN] Could not connect to MySQL:", e)
    sql = None
    connection = None
    DB_OK = False

# ----------------------------
# Model wrapper
# ----------------------------
def predict_image(image_path):
    tried = []
    try:
        main_fn = getattr(model, "main", None)
        if main_fn is None:
            raise RuntimeError("model.main not found")
        sig = inspect.signature(main_fn)
        params = len(sig.parameters)
        if params == 1:
            pname = next(iter(sig.parameters.keys())).lower()
            if any(k in pname for k in ("path", "filename", "fname", "file")):
                tried.append("main(path)")
                res = main_fn(image_path)
            elif any(k in pname for k in ("img", "image", "pil", "im")):
                tried.append("main(PIL)")
                pil = Image.open(image_path)
                res = main_fn(pil)
            else:
                tried.append("main(path)")
                try:
                    res = main_fn(image_path)
                except TypeError:
                    tried.append("main(PIL)")
                    pil = Image.open(image_path)
                    res = main_fn(pil)
        elif params == 0:
            tried.append("main()")
            res = main_fn()
        else:
            tried.append("main(path)")
            res = main_fn(image_path)

        label = None; cls = None
        if isinstance(res, (tuple, list)):
            if len(res) >= 2:
                label, cls = res[0], res[1]
            elif len(res) == 1:
                label, cls = res[0], None
        elif isinstance(res, dict):
            label = res.get('label') or res.get('prediction') or res.get('value')
            cls = res.get('class') or res.get('classes') or res.get('label_id') or None
        else:
            label, cls = res, None
        try:
            if cls is not None and isinstance(cls, str) and cls.isdigit():
                cls = int(cls)
        except Exception:
            pass
        print(f"[MODEL] success ({tried[-1] if tried else 'unknown'}) -> label={label}, class={cls}")
        return label, cls
    except Exception as e:
        print("[ERROR] predict_image failed (tried: %s): %s" % (tried, e))
        traceback.print_exc()
        return f"Model error: {e}", None

# ----------------------------
# DB schema helpers (auto ALTER)
# ----------------------------
def ensure_patient_schema_and_columns():
    if not DB_OK:
        return
    try:
        sql.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user VARCHAR(255),
                name VARCHAR(255),
                age INT,
                gender VARCHAR(20),
                contact VARCHAR(50),
                notes TEXT
            )
        """)
        connection.commit()
    except Exception as e:
        print("[DB] ensure patients table warning:", e)
    try:
        sql.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'patients'
              AND COLUMN_NAME = 'diagnosis'
        """)
        if sql.fetchone()[0] == 0:
            try:
                sql.execute("ALTER TABLE patients ADD COLUMN diagnosis VARCHAR(255) NULL")
                connection.commit()
                print("[DB] Added 'diagnosis' column to patients")
            except Exception as e:
                print("[DB] Could not add 'diagnosis' column:", e)
    except Exception as e:
        print("[DB] diagnosis column check warning:", e)
    try:
        sql.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'patients'
              AND COLUMN_NAME = 'diagnosis_class'
        """)
        if sql.fetchone()[0] == 0:
            try:
                sql.execute("ALTER TABLE patients ADD COLUMN diagnosis_class VARCHAR(64) NULL")
                connection.commit()
                print("[DB] Added 'diagnosis_class' column to patients")
            except Exception as e:
                print("[DB] Could not add 'diagnosis_class' column:", e)
    except Exception as e:
        print("[DB] diagnosis_class column check warning:", e)
    try:
        sql.execute("""
            CREATE TABLE IF NOT EXISTS diagnosis_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                patient_id INT,
                diagnosis VARCHAR(255),
                diagnosis_class VARCHAR(64),
                test_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        """)
        connection.commit()
    except Exception as e:
        print("[DB] diagnosis_history creation warning:", e)

def ensure_predict_column():
    if not DB_OK:
        return
    try:
        sql.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'THEGREAT'
              AND COLUMN_NAME = 'PREDICT'
        """)
        if sql.fetchone()[0] == 0:
            try:
                sql.execute("ALTER TABLE THEGREAT ADD COLUMN PREDICT VARCHAR(255) NULL")
                connection.commit()
                print("[DB] Added PREDICT column to THEGREAT")
            except Exception as e:
                print("[DB] Could not add PREDICT column:", e)
    except Exception as e:
        print("[DB] ensure_predict_column warning:", e)

# ----------------------------
# PDF generator (Layout A: Name, Gender, blank, Age, Contact)
# ----------------------------
def generate_report_pdf(patient_row, image_path, diagnosis, diagnosis_class, out_path):
    try:
        if not patient_row:
            name = "Unknown"; age = ""; gender = ""; contact = ""; notes = ""
        else:
            try:
                name = patient_row[2] if len(patient_row) > 2 else ""
                age = str(patient_row[3]) if len(patient_row) > 3 and patient_row[3] is not None else ""
                gender = patient_row[4] if len(patient_row) > 4 else ""
                contact = patient_row[5] if len(patient_row) > 5 else ""
                notes = patient_row[6] if len(patient_row) > 6 and patient_row[6] else ""
            except Exception:
                name = str(patient_row); age = ""; gender = ""; contact = ""; notes = ""

        doc = SimpleDocTemplate(out_path, pagesize=A4, title="Medical Report",
                                leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        left_style = ParagraphStyle(name='Left', parent=styles['Normal'], alignment=TA_LEFT, leading=12)

        elements = []
        elements.append(Paragraph("<b>MEDICAL REPORT</b>", styles['Title']))
        elements.append(Spacer(1, 8))

        elements.append(Paragraph("<b>SECTION A - Patient Information</b>", styles['Heading4']))
        # Layout A: Name & Gender, blank line, then Age & Contact
        data_a = [
            ["Full name:", name, "Gender:", gender],
            ["Age:", age, "Contact:", contact]
        ]
        t_a = Table(data_a, colWidths=[80, 220, 80, 140], hAlign='LEFT')
        t_a.setStyle(TableStyle([
            ("GRID", (0,0), (-1,-1), 0.5, colors.black),
            ("ALIGN", (0,0), (-1,-1), "LEFT"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ]))
        elements.append(t_a)
        elements.append(Spacer(1, 10))

        elements.append(Paragraph("<b>SECTION B - Examination / Diagnosis</b>", styles['Heading4']))
        test_date = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        diag_text = f"{diagnosis} (class {diagnosis_class})" if diagnosis_class else f"{diagnosis}"
        data_b = [["Diagnosis:", diag_text], ["Test Date:", test_date]]
        t_b = Table(data_b, colWidths=[100, 360], hAlign='LEFT')
        t_b.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.5, colors.black), ("ALIGN", (0,0), (-1,-1), "LEFT")]))
        elements.append(t_b)
        elements.append(Spacer(1, 10))

        elements.append(Paragraph("<b>Relevant notes:</b>", styles['Heading5']))
        if notes:
            elements.append(Paragraph(notes.replace("\n", "<br/>"), left_style))
        else:
            elements.append(Paragraph("None", left_style))
        elements.append(Spacer(1, 12))

        if image_path and os.path.exists(image_path):
            try:
                elements.append(Paragraph("<b>Uploaded Retinal Image</b>", styles['Heading5']))
                img = RLImage(image_path, width=300, height=300)
                elements.append(img)
            except Exception as e:
                print("[PDF] Could not attach image:", e)

        doc.build(elements)
        print(f"[PDF] Saved: {out_path}")
        return True, None
    except Exception as e:
        print("[PDF ERROR]", e)
        traceback.print_exc()
        return False, str(e)

# ----------------------------
# UI constants
# ----------------------------
APP_TITLE = "Diabetic Retinopathy Detection"
BG_COLOR = "#eef6f6"
ACCENT = "#074E96"
CARD_BG = "white"
FONT_HEAD = ("Segoe UI", 26, "bold")
FONT_LABEL = ("Segoe UI", 18)
FONT_INPUT = ("Segoe UI", 17)

# ----------------------------
# Main Application
# ----------------------------
class App(tk := Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        try:
            self.state('zoomed')
        except Exception:
            try:
                self.attributes('-zoomed', True)
            except Exception:
                pass
        self.minsize(1024, 600)
        self.configure(bg=BG_COLOR)

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background=BG_COLOR)
        style.configure('Card.TFrame', background=CARD_BG, relief='flat')
        style.configure('TLabel', background=BG_COLOR, font=FONT_LABEL)
        style.configure('Header.TLabel', font=FONT_HEAD, background=BG_COLOR)
        style.configure('Accent.TButton', background=ACCENT, foreground='white')
        style.map('Accent.TButton', background=[('active', "#045f93")])
        style.configure('TButton', font=FONT_INPUT, padding=6)

        container = ttk.Frame(self)
        container.pack(fill='both', expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)
        self.container = container

        if DB_OK:
            ensure_patient_schema_and_columns()
            ensure_predict_column()

        self.user = None
        self.frames = {}
        for F in (LoginPage, SignupPage, PatientListPage, PatientFormPage, UploadPage):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky='nsew')

        self.show_frame("LoginPage")

    def show_frame(self, name, **kwargs):
        frame = self.frames.get(name)
        if not frame:
            return
        if hasattr(frame, "set_context"):
            frame.set_context(**kwargs)
        frame.tkraise()

# ----------------------------
# BasePage
# ----------------------------
class BasePage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
    def card(self, parent, padding=(20,20)):
        card = ttk.Frame(parent, style='Card.TFrame', padding=padding)
        return card

# ----------------------------
# LoginPage (with logo + eye icon)
# ----------------------------
class LoginPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        header = ttk.Label(self, text="Diabetic Retinopathy Detection", style='Header.TLabel')
        header.pack(pady=(12,6))

        main_card = self.card(self)
        main_card.pack(fill='both', expand=True, padx=36, pady=12)
        main_card.columnconfigure(0, weight=1)
        main_card.columnconfigure(1, weight=1)

        left = ttk.Frame(main_card, style='Card.TFrame')
        left.grid(row=0, column=0, sticky='nsew', padx=(10,20), pady=10)
        eye_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "eye_icon.png")
        try:
            pil = Image.open(eye_path).resize((420,420))
            tkimg = ImageTk.PhotoImage(pil)
            lbl_img = ttk.Label(left, image=tkimg)
            lbl_img.image = tkimg
            lbl_img.pack(expand=True)
        except Exception:
            pass

        right = ttk.Frame(main_card, style='Card.TFrame')
        right.grid(row=0, column=1, sticky='nsew', padx=(20,10), pady=10)
        right.columnconfigure(0, weight=1)

        # show generated logo on top-right
        logo_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "logo_small.png")
        try:
            pil_logo = Image.open(logo_path).resize((180,54))
            tk_logo = ImageTk.PhotoImage(pil_logo)
            lbl_logo = ttk.Label(right, image=tk_logo)
            lbl_logo.image = tk_logo
            lbl_logo.pack(anchor='ne', pady=(6,6), padx=(0,12))
        except Exception:
            pass

        # larger fonts for signup entries
        lbl_font = ("Segoe UI", 14)
        entry_font = ("Segoe UI", 13)

        ttk.Label(right, text="Login", font=("Segoe UI", 18, "bold")).pack(anchor='w', pady=(6,8), padx=8)
        form = ttk.Frame(right)
        form.pack(fill='x', padx=12, pady=6)

        ttk.Label(form, text="Username", font=lbl_font).grid(row=0, column=0, sticky='w')
        self.username_var = StringVar()
        ttk.Entry(form, textvariable=self.username_var, font=entry_font).grid(row=1, column=0, pady=(6,12), sticky='ew')

        ttk.Label(form, text="Password", font=lbl_font).grid(row=2, column=0, sticky='w')
        self.password_var = StringVar()
        ttk.Entry(form, textvariable=self.password_var, show='*', font=entry_font).grid(row=3, column=0, pady=(6,12), sticky='ew')

        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=4, column=0, pady=8, sticky='w')
        ttk.Button(btn_frame, text="Login", style='Accent.TButton', command=self.handle_login).pack(side='left', padx=(0,8))
        ttk.Button(btn_frame, text="Create account", command=lambda: controller.show_frame("SignupPage")).pack(side='left')

        hint = ttk.Label(right, text="Don't have an account? Click Create account.", foreground='#444')
        hint.pack(anchor='s', pady=(12,0))

    def handle_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        if not username or not password:
            messagebox.showwarning("Validation", "Please enter username and password.")
            return
        if not DB_OK:
            messagebox.showerror("Database", "Database connection not available.")
            return
        try:
            sql.execute("SELECT * FROM THEGREAT")
            rows = sql.fetchall()
            ok_user = any(r[0] == username and r[1] == password for r in rows)
            if ok_user:
                self.controller.user = username
                messagebox.showinfo("Welcome", f"Hello {username}, you are logged in.")
                self.controller.show_frame("PatientListPage")
            else:
                messagebox.showerror("Login failed", "Invalid username or password.")
        except Exception as e:
            messagebox.showerror("DB Error", f"Database query failed: {e}")
            print("DB error:", e)

# ----------------------------
# SignupPage (larger font & centered)
# ----------------------------
class SignupPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        header = ttk.Label(self, text="Create Account", style='Header.TLabel')
        header.pack(pady=(12,6))

        card = self.card(self)
        card.pack(fill='both', expand=True, padx=80, pady=20)
        card.columnconfigure(0, weight=1)

        frm_outer = ttk.Frame(card)
        frm_outer.pack(fill='both', expand=True)
        frm_outer.columnconfigure(0, weight=1)
        frm_outer.rowconfigure(0, weight=1)

        frm = ttk.Frame(frm_outer)
        frm.grid(row=0, column=0, sticky='nsew')

        inner = ttk.Frame(frm)
        inner.place(relx=0.5, rely=0.5, anchor='center')

        # larger fonts for signup entries
        lbl_font = ("Segoe UI", 14)
        entry_font = ("Segoe UI", 13)

        ttk.Label(inner, text="Choose a username", font=lbl_font).grid(row=0, column=0, sticky='w')
        self.new_user = StringVar()
        ttk.Entry(inner, textvariable=self.new_user, width=36, font=entry_font).grid(row=1, column=0, pady=(6,12))

        ttk.Label(inner, text="Choose a password", font=lbl_font).grid(row=2, column=0, sticky='w')
        self.new_pass = StringVar()
        ttk.Entry(inner, textvariable=self.new_pass, width=36, show='*', font=entry_font).grid(row=3, column=0, pady=(6,12))

        ttk.Label(inner, text="Confirm password", font=lbl_font).grid(row=4, column=0, sticky='w')
        self.confirm_pass = StringVar()
        ttk.Entry(inner, textvariable=self.confirm_pass, width=36, show='*', font=entry_font).grid(row=5, column=0, pady=(6,16))

        btn_frame = ttk.Frame(inner)
        btn_frame.grid(row=6, column=0, pady=6, sticky='w')
        ttk.Button(btn_frame, text="Sign up", style='Accent.TButton', command=self.handle_signup).pack(side='left', padx=(0,8))
        ttk.Button(btn_frame, text="Back to Login", command=lambda: controller.show_frame("LoginPage")).pack(side='left')

    def handle_signup(self):
        u = self.new_user.get().strip()
        p = self.new_pass.get().strip()
        c = self.confirm_pass.get().strip()
        if not u or not p:
            messagebox.showwarning("Validation", "Enter username and password.")
            return
        if p != c:
            messagebox.showwarning("Validation", "Passwords do not match.")
            return
        if not DB_OK:
            messagebox.showerror("Database", "DB connection not available.")
            return
        try:
            sql.execute("SELECT * FROM THEGREAT")
            data = sql.fetchall()
            if any(row[0] == u for row in data):
                messagebox.showinfo("Exists", "Username already registered. Choose another.")
                return
            query = "INSERT INTO THEGREAT (USERNAME, PASSWORD) VALUES(%s, %s)"
            sql.execute(query, (u, p))
            connection.commit()
            messagebox.showinfo("Success", "Account created — you can now log in.")
            self.controller.show_frame("LoginPage")
        except Exception as e:
            messagebox.showerror("DB Error", f"Could not create account: {e}")
            print("Signup DB error:", e)

# ----------------------------
# PatientListPage (visual lines / alternating rows)
# ----------------------------
class PatientListPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        topbar = ttk.Frame(self)
        topbar.pack(fill='x', padx=12, pady=10)
        ttk.Label(topbar, text="Patients", style='Header.TLabel').pack(side='left')
        ttk.Button(topbar, text="Logout", command=self.logout).pack(side='right')
        ttk.Button(topbar, text="Add Patient", command=lambda: controller.show_frame("PatientFormPage", patient=None)).pack(side='right', padx=8)

        self.card_frame = self.card(self, padding=(10,10))
        self.card_frame.pack(fill='both', expand=True, padx=20, pady=10)
        self.card_frame.columnconfigure(0, weight=1)
        self.card_frame.rowconfigure(0, weight=1)

        cols = ("id", "name", "age", "gender", "contact", "diagnosis", "diag_class")
        self.tree = ttk.Treeview(self.card_frame, columns=cols, show='headings', selectmode='browse')
        headings = ["ID", "Name", "Age", "Gender", "Contact", "Diagnosis", "Class"]
        widths = [60, 260, 80, 100, 160, 220, 80]
        for c, h, w in zip(cols, headings, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor='w')
        self.tree.grid(row=0, column=0, sticky='nsew', padx=(6,0), pady=6)

        # add striped rows via tags
        self.tree.tag_configure('oddrow', background='#ffffff')
        self.tree.tag_configure('evenrow', background='#f6fafd')

        scrollbar = ttk.Scrollbar(self.card_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky='ns', padx=(6,0), pady=6)

        btn_panel = ttk.Frame(self.card_frame)
        btn_panel.grid(row=0, column=2, sticky='ns', padx=8, pady=6)
        ttk.Button(btn_panel, text="Edit", command=self.edit_selected).pack(fill='x', pady=6)
        ttk.Button(btn_panel, text="Upload Image", command=self.upload_selected).pack(fill='x', pady=6)
        ttk.Button(btn_panel, text="Delete", command=self.delete_selected).pack(fill='x', pady=6)

        self.refresh()

    def set_context(self, **kwargs):
        self.refresh()

    def refresh(self):
        try:
            sql.execute("SHOW TABLES LIKE 'patients'")
            if sql.fetchone() is None:
                sql.execute("""CREATE TABLE IF NOT EXISTS patients (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user VARCHAR(255),
                            name VARCHAR(255),
                            age INT,
                            gender VARCHAR(20),
                            contact VARCHAR(50),
                            notes TEXT,
                            diagnosis VARCHAR(255),
                            diagnosis_class VARCHAR(64)
                            )""")
                connection.commit()
            sql.execute("SELECT id, name, age, gender, contact, diagnosis, diagnosis_class FROM patients WHERE user = %s", (self.controller.user,))
            rows = sql.fetchall()
        except Exception as e:
            print("Patient load error:", e)
            rows = []
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, r in enumerate(rows):
            tag = 'evenrow' if idx % 2 == 0 else 'oddrow'
            diag_cls_display = r[6] if len(r) > 6 and r[6] is not None else ""
            self.tree.insert('', 'end', values=(r[0], r[1], r[2], r[3], r[4], r[5] or "", diag_cls_display), tags=(tag,))

    def logout(self):
        self.controller.user = None
        messagebox.showinfo("Logout", "You have been logged out.")
        self.controller.show_frame("LoginPage")

    def get_selected_patient_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Please select a patient first.")
            return None
        row = self.tree.item(sel[0])['values']
        return row[0]

    def edit_selected(self):
        pid = self.get_selected_patient_id()
        if pid:
            try:
                sql.execute("SELECT * FROM patients WHERE id = %s", (pid,))
                p = sql.fetchone()
            except Exception:
                p = None
            self.controller.show_frame("PatientFormPage", patient=p)

    def upload_selected(self):
        pid = self.get_selected_patient_id()
        if pid:
            try:
                sql.execute("SELECT * FROM patients WHERE id = %s", (pid,))
                p = sql.fetchone()
            except Exception:
                p = None
            self.controller.show_frame("UploadPage", patient=p)

    def delete_selected(self):
        pid = self.get_selected_patient_id()
        if not pid:
            return
        if messagebox.askyesno("Confirm", "Delete selected patient?"):
            try:
                sql.execute("DELETE FROM patients WHERE id = %s", (pid,))
                connection.commit()
                messagebox.showinfo("Deleted", "Patient deleted.")
                self.refresh()
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete: {e}")


# ----------------------------
# PatientFormPage
# ----------------------------
class PatientFormPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        header = ttk.Frame(self)
        header.pack(fill='x', padx=12, pady=10)
        ttk.Label(header, text="Patient Details", style='Header.TLabel').pack(side='left')
        ttk.Button(header, text="Back", command=lambda: controller.show_frame("PatientListPage")).pack(side='right')

        self.card_frame = self.card(self)
        self.card_frame.pack(fill='both', expand=True, padx=20, pady=12)
        self.card_frame.columnconfigure(0, weight=1)
        self.card_frame.columnconfigure(1, weight=1)

        frm = ttk.Frame(self.card_frame)
        frm.pack(fill='both', expand=True, padx=20, pady=12)
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=2)

        ttk.Label(frm, text="Full name").grid(row=0, column=0, sticky='w', padx=6, pady=6)
        self.name_var = StringVar()
        ttk.Entry(frm, textvariable=self.name_var).grid(row=0, column=1, pady=6, sticky='ew')

        ttk.Label(frm, text="Age").grid(row=1, column=0, sticky='w', padx=6, pady=6)
        self.age_var = StringVar()
        ttk.Entry(frm, textvariable=self.age_var, width=12).grid(row=1, column=1, pady=6, sticky='w')

        ttk.Label(frm, text="Gender").grid(row=2, column=0, sticky='w', padx=6, pady=6)
        self.gender_var = StringVar()
        ttk.Combobox(frm, textvariable=self.gender_var, values=["Male","Female","Other"]).grid(row=2, column=1, pady=6, sticky='w')

        ttk.Label(frm, text="Contact").grid(row=3, column=0, sticky='w', padx=6, pady=6)
        self.contact_var = StringVar()
        ttk.Entry(frm, textvariable=self.contact_var).grid(row=3, column=1, pady=6, sticky='ew')

        ttk.Label(frm, text="Notes").grid(row=4, column=0, sticky='nw', padx=6, pady=6)
        self.notes_text = Text(frm, height=8)
        self.notes_text.grid(row=4, column=1, pady=6, sticky='ew')

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=5, column=1, pady=10, sticky='e')
        ttk.Button(btn_frame, text="Save", style='Accent.TButton', command=self.save_patient).pack(side='left', padx=(0,8))
        ttk.Button(btn_frame, text="Cancel", command=lambda: controller.show_frame("PatientListPage")).pack(side='left')

        self.current_patient = None

    def set_context(self, patient=None):
        self.current_patient = patient
        if patient:
            try:
                self.name_var.set(patient[2])
                self.age_var.set(str(patient[3]) if patient[3] is not None else "")
                self.gender_var.set(patient[4] or "")
                self.contact_var.set(patient[5] or "")
                self.notes_text.delete('1.0', END)
                self.notes_text.insert('1.0', patient[6] or "")
            except Exception:
                self.name_var.set(patient[1] if len(patient) > 1 else "")
                self.age_var.set(patient[2] if len(patient) > 2 else "")
                self.gender_var.set(patient[3] if len(patient) > 3 else "")
                self.contact_var.set(patient[4] if len(patient) > 4 else "")
                self.notes_text.delete('1.0', END)
        else:
            self.name_var.set("")
            self.age_var.set("")
            self.gender_var.set("")
            self.contact_var.set("")
            self.notes_text.delete('1.0', END)

    def save_patient(self):
        name = self.name_var.get().strip()
        age = self.age_var.get().strip() or None
        gender = self.gender_var.get().strip()
        contact = self.contact_var.get().strip()
        notes = self.notes_text.get('1.0', END).strip()
        if not name:
            messagebox.showwarning("Validation", "Patient name is required.")
            return
        if not DB_OK:
            messagebox.showerror("DB", "Database not available.")
            return
        try:
            if self.current_patient:
                pid = self.current_patient[0]
                sql.execute("""UPDATE patients SET name=%s, age=%s, gender=%s, contact=%s, notes=%s WHERE id=%s""",
                            (name, age, gender, contact, notes, pid))
                connection.commit()
                messagebox.showinfo("Saved", "Patient updated.")
            else:
                sql.execute("""INSERT INTO patients (user, name, age, gender, contact, notes) VALUES (%s,%s,%s,%s,%s,%s)""",
                            (self.controller.user, name, age, gender, contact, notes))
                connection.commit()
                messagebox.showinfo("Saved", "Patient added.")
            self.controller.show_frame("PatientListPage")
        except Exception as e:
            messagebox.showerror("DB Error", f"Could not save patient: {e}")
            print("Save patient error:", e)

# ----------------------------
# UploadPage
# ----------------------------
class UploadPage(BasePage):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        header = ttk.Frame(self)
        header.pack(fill='x', padx=12, pady=10)
        ttk.Label(header, text="Upload Image for Diagnosis", style='Header.TLabel').pack(side='left')
        ttk.Button(header, text="Back", command=lambda: controller.show_frame("PatientListPage")).pack(side='right')

        self.card_frame = self.card(self)
        self.card_frame.pack(fill='both', expand=True, padx=20, pady=12)
        frm = ttk.Frame(self.card_frame)
        frm.pack(fill='both', expand=True, padx=20, pady=12)
        frm.columnconfigure(1, weight=1)

        self.patient_info_label = ttk.Label(frm, text="Patient: (none)", font=("Segoe UI", 12))
        self.patient_info_label.grid(row=0, column=0, columnspan=3, sticky='w', pady=(0,8))

        ttk.Button(frm, text="Select Image...", command=self.select_image).grid(row=1, column=0, sticky='w')
        self.img_path_var = StringVar()
        ttk.Entry(frm, textvariable=self.img_path_var).grid(row=1, column=1, padx=(8,0), sticky='ew')

        ttk.Button(frm, text="Run Diagnosis", style='Accent.TButton', command=self.run_diagnosis).grid(row=2, column=0, pady=(12,0), sticky='w')
        self.result_label = ttk.Label(frm, text="", font=("Segoe UI", 12, "bold"))
        self.result_label.grid(row=3, column=0, columnspan=2, sticky='w', pady=(12,0))

        preview_frame = ttk.Frame(frm)
        preview_frame.grid(row=1, column=2, rowspan=4, padx=(12,0), sticky='ne')
        self.preview_lbl = ttk.Label(preview_frame)
        self.preview_lbl.pack()

        self.current_patient = None

    def set_context(self, patient=None):
        self.current_patient = patient
        if patient:
            name = patient[2] if len(patient) > 2 else str(patient)
            diag = patient[7] if len(patient) > 7 else None
            cls = patient[8] if len(patient) > 8 else None
            display = f"Patient: {name}"
            if diag:
                display += f" — Last: {diag} (class {cls})" if cls else f" — Last: {diag}"
            self.patient_info_label.config(text=display)
        else:
            self.patient_info_label.config(text="Patient: (none)")
        self.img_path_var.set("")
        self.result_label.config(text="")
        self.preview_lbl.config(image='')

    def select_image(self):
        path = askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg"), ("All files","*.*")])
        if path:
            self.img_path_var.set(path)
            try:
                pil = Image.open(path)
                pil.thumbnail((320,320))
                tkii = ImageTk.PhotoImage(pil)
                self.preview_lbl.image = tkii
                self.preview_lbl.config(image=tkii)
            except Exception as e:
                print("Preview error:", e)

    def run_diagnosis(self):
        path = self.img_path_var.get()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Select Image", "Please select an image first.")
            return
        value, classes = predict_image(path)
        cls_str = str(classes) if classes is not None else ""
        display_text = f"Diagnosis: {value}"
        if classes is not None:
            display_text += f" (class {cls_str})"
        self.result_label.config(text=display_text)

        try:
            patient_row = self.current_patient
            if not patient_row:
                pl = self.controller.frames.get("PatientListPage")
                if pl:
                    pid = pl.get_selected_patient_id()
                    if pid:
                        sql.execute("SELECT * FROM patients WHERE id = %s", (pid,))
                        patient_row = sql.fetchone()
            if patient_row:
                pid = patient_row[0]
                sql.execute("UPDATE patients SET diagnosis=%s, diagnosis_class=%s WHERE id=%s", (str(value), cls_str, pid))
                sql.execute("INSERT INTO diagnosis_history (patient_id, diagnosis, diagnosis_class) VALUES (%s, %s, %s)", (pid, str(value), cls_str))
                connection.commit()
        except Exception as e:
            print("[DB] Could not update patient diagnosis:", e)

        try:
            if self.controller.user:
                ensure_predict_column()
                sql.execute("UPDATE THEGREAT SET PREDICT=%s WHERE USERNAME=%s", (str(value), self.controller.user))
                connection.commit()
        except Exception as e:
            print("[DB] Could not update THEGREAT.PREDICT:", e)

        try:
            reports_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "reports")
            os.makedirs(reports_dir, exist_ok=True)
            safe_name = (patient_row[2] if patient_row and len(patient_row) > 2 else (self.controller.user or "patient")).replace(" ", "_")
            ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            out_file = os.path.join(reports_dir, f"report_{safe_name}_{ts}.pdf")
            ok, err = generate_report_pdf(patient_row, path, str(value), cls_str, out_file)
            if ok:
                try:
                    if sys.platform.startswith('win'):
                        os.startfile(out_file)
                    else:
                        webbrowser.open_new(out_file)
                except Exception:
                    pass
                messagebox.showinfo("Report saved", f"PDF report created:\n{out_file}")
            else:
                messagebox.showwarning("PDF error", f"Could not create report: {err}")
        except Exception as e:
            print("Report generation error:", e)
            traceback.print_exc()


# ----------------------------
# Start app
# ----------------------------
def main():
    app = App()
    app.mainloop()

if __name__ == '__main__':
    main()
