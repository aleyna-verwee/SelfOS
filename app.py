from flask import Flask, render_template, request, redirect, url_for, send_file, session
import sqlite3, io, csv, statistics
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "selfos-secret"
DB = "selfos.db"

# ---------------- DB helpers ----------------
def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def column_exists(con, table, col):
    row = con.execute(f"PRAGMA table_info({table})").fetchall()
    cols = {r["name"] for r in row}
    return col in cols

def init_db():
    with get_db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            lang TEXT DEFAULT 'fr',
            age INTEGER,
            gender TEXT,         -- 'female' | 'male' | 'nonbinary' | 'other'
            mbti TEXT,           -- ex: INTJ
            created_at TEXT
        )""")
        # auto-migration si la table existe déjà
        for col, typ in [("age","INTEGER"),("gender","TEXT"),("mbti","TEXT")]:
            if not column_exists(con, "users", col):
                con.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        con.execute("""CREATE TABLE IF NOT EXISTS moods(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, mood INTEGER, sleep REAL, note TEXT,
            user_email TEXT
        )""")
init_db()

# ---------------- i18n ----------------
LANGS = {
  "fr": {
    "language":"Langue","email":"E-mail","password":"Mot de passe","connect":"Se connecter",
    "register":"Créer un compte","have_account":"Déjà un compte ?","no_account":"Pas de compte ?",
    "login_invalid":"Identifiants invalides.","title":"Tableau de bord émotionnel",
    "mood":"Humeur","sleep":"Sommeil (h)","note":"Note","add":"Ajouter",
    "avg7":"Moyenne 7 jours","avg30":"Moyenne 30 jours","avg90":"Moyenne 90 jours",
    "logout":"Se déconnecter","export_csv":"Exporter CSV","export_pdf":"Exporter PDF","delete":"Supprimer historique",
    "assistant":"Assistant IA","history":"Historique","need_more":"Ajoute 3–5 entrées pour débloquer des insights ✨",
    "great":"Belle dynamique 💫 Continue : sommeil régulier, marche 20–30 min, hydratation.",
    "low":"Énergie basse. Ce soir : 20–30 min de marche, douche chaude, coucher plus tôt.",
    "stable":"Stabilité correcte. Mini-action +1 : respiration 4-7-8, 10 squats, écrire à un proche.",
    "age":"Âge","gender":"Genre","mbti":"MBTI","female":"Femme","male":"Homme","nonbinary":"Non binaire","other":"Autre"
  },
  "en": {
    "language":"Language","email":"Email","password":"Password","connect":"Sign in",
    "register":"Create account","have_account":"Already have an account?","no_account":"No account?",
    "login_invalid":"Invalid credentials.","title":"Emotional Dashboard",
    "mood":"Mood","sleep":"Sleep (h)","note":"Note","add":"Add",
    "avg7":"7-day average","avg30":"30-day average","avg90":"90-day average",
    "logout":"Logout","export_csv":"Export CSV","export_pdf":"Export PDF","delete":"Delete history",
    "assistant":"AI Assistant","history":"History","need_more":"Add 3–5 entries to unlock insights ✨",
    "great":"Great momentum 💫 Keep consistent sleep, 20–30 min walk, hydration.",
    "low":"Low energy. Tonight: 20–30 min walk, warm shower, earlier bedtime.",
    "stable":"Fairly stable. +1 micro-action: 4-7-8 breathing, 10 squats, text a friend.",
    "age":"Age","gender":"Gender","mbti":"MBTI","female":"Female","male":"Male","nonbinary":"Non-binary","other":"Other"
  },
  "nl": {
    "language":"Taal","email":"E-mail","password":"Wachtwoord","connect":"Inloggen",
    "register":"Account aanmaken","have_account":"Al een account?","no_account":"Nog geen account?",
    "login_invalid":"Ongeldige inloggegevens.","title":"Stemmingsdashboard",
    "mood":"Stemming","sleep":"Slaap (u)","note":"Notitie","add":"Toevoegen",
    "avg7":"Gem. laatste 7","avg30":"Gem. 30 dagen","avg90":"Gem. 90 dagen",
    "logout":"Afmelden","export_csv":"Exporteer CSV","export_pdf":"Exporteer PDF","delete":"Historiek verwijderen",
    "assistant":"AI Assistent","history":"Historiek","need_more":"Voeg 3–5 registraties toe voor inzichten ✨",
    "great":"Mooi momentum 💫 Vast slaapritme, 20–30 min wandelen, hydratatie.",
    "low":"Lage energie. Vanavond: 20–30 min wandelen, warme douche, vroeger slapen.",
    "stable":"Vrij stabiel. +1 micro-actie: 4-7-8 ademhaling, 10 squats, bericht sturen.",
    "age":"Leeftijd","gender":"Gender","mbti":"MBTI","female":"Vrouw","male":"Man","nonbinary":"Non-binair","other":"Overig"
  },
  # login/inscription seulement pour ces langues (labels d’auth propres)
  "de": {"language":"Sprache","email":"E-Mail","password":"Passwort","connect":"Anmelden",
         "register":"Konto erstellen","have_account":"Schon ein Konto?","no_account":"Noch kein Konto?",
         "login_invalid":"Ungültige Zugangsdaten."},
  "es": {"language":"Idioma","email":"Correo","password":"Contraseña","connect":"Iniciar sesión",
         "register":"Crear cuenta","have_account":"¿Ya tienes cuenta?","no_account":"¿No tienes cuenta?",
         "login_invalid":"Credenciales no válidas."},
  "ko": {"language":"언어","email":"이메일","password":"비밀번호","connect":"로그인",
         "register":"계정 만들기","have_account":"이미 계정이 있나요?","no_account":"계정이 없나요?",
         "login_invalid":"자격 증명이 올바르지 않습니다."},
  "tr": {"language":"Dil","email":"E-posta","password":"Şifre","connect":"Giriş yap",
         "register":"Hesap oluştur","have_account":"Zaten hesabın var mı?","no_account":"Hesabın yok mu?",
         "login_invalid":"Geçersiz bilgiler."},
  "zh": {"language":"语言","email":"邮箱","password":"密码","connect":"登录",
         "register":"创建账户","have_account":"已有账户？","no_account":"没有账户？",
         "login_invalid":"凭证无效。"}
}

def t(key):
    lang = session.get("lang","fr")
    base = LANGS.get(lang) or LANGS["en"]
    return base.get(key, LANGS["en"].get(key, key))

app.jinja_env.globals.update(t=t)

# ---------------- AI ----------------
def analyse(rows):
    if not rows: return t("need_more")
    moods = [int(r["mood"]) for r in rows]
    avg = statistics.mean(moods)
    if avg >= 7.5: return t("great")
    if avg <= 4.0: return t("low")
    recent = rows[-7:]
    sleeps = [float(r["sleep"]) for r in recent if r["sleep"] is not None]
    msg = t("stable")
    if sleeps and statistics.mean(sleeps) < 6.5:
        extra = {"fr":" 💤 Ajoute +30–45 min de sommeil.",
                 "en":" 💤 Increase sleep by +30–45 min.",
                 "nl":" 💤 +30–45 min extra slaap."}
        msg += extra.get(session.get("lang","fr"), "")
    return msg

# ---------------- Routes ----------------
@app.route("/")
def index():
    if "email" not in session: return redirect(url_for("login"))
    with get_db() as con:
        rows = con.execute("SELECT * FROM moods WHERE user_email=? ORDER BY ts ASC",
                           (session["email"],)).fetchall()
    now = datetime.now()
    def avg_since(days):
        cut = now - timedelta(days=days)
        data = [r["mood"] for r in rows if datetime.fromisoformat(r["ts"]) > cut]
        return round(sum(data)/len(data),1) if data else 0
    return render_template("index.html",
        rows=rows, ai=analyse(rows),
        avg7=avg_since(7), avg30=avg_since(30), avg90=avg_since(90)
    )

@app.route("/add", methods=["POST"])
def add():
    if "email" not in session: return redirect(url_for("login"))
    mood = request.form.get("mood")
    sleep = request.form.get("sleep") or 0
    note = request.form.get("note")
    ts = datetime.now().isoformat(timespec="minutes")
    with get_db() as con:
        con.execute("INSERT INTO moods(ts,mood,sleep,note,user_email) VALUES (?,?,?,?,?)",
                    (ts, mood, sleep, note, session["email"]))
    return redirect(url_for("index"))

@app.route("/delete")
def delete():
    if "email" not in session: return redirect(url_for("login"))
    with get_db() as con:
        con.execute("DELETE FROM moods WHERE user_email=?", (session["email"],))
    return redirect(url_for("index"))

# -------- Auth: email + password + age/gender/mbti ----------
def valid_age(v):
    try:
        n = int(v)
        return 12 <= n <= 100
    except:
        return False

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pwd   = (request.form.get("password") or "").strip()
        lang  = request.form.get("lang","fr")
        age   = request.form.get("age") or None
        gender= request.form.get("gender") or None
        mbti  = (request.form.get("mbti") or "").upper() or None

        if not email or "@" not in email:
            return render_template("register.html", error="E-mail invalide.")
        if len(pwd) < 6:
            return render_template("register.html", error="Mot de passe : 6 caractères min.")
        if age and not valid_age(age):
            return render_template("register.html", error="Âge entre 12 et 100.")

        with get_db() as con:
            try:
                con.execute("""INSERT INTO users(email,password_hash,lang,age,gender,mbti,created_at)
                               VALUES (?,?,?,?,?,?,?)""",
                            (email, generate_password_hash(pwd), lang, age, gender, mbti, datetime.now().isoformat()))
            except sqlite3.IntegrityError:
                return render_template("register.html", error="E-mail déjà enregistré.")

        session["email"] = email
        session["lang"]  = lang
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pwd   = (request.form.get("password") or "").strip()
        lang  = request.form.get("lang","fr")
        session["lang"] = lang
        with get_db() as con:
            row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if row and check_password_hash(row["password_hash"], pwd):
            session["email"] = email
            session["lang"]  = row["lang"] or lang
            return redirect(url_for("index"))
        return render_template("login.html", error=t("login_invalid"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----- Export -----
@app.route("/export_csv")
def export_csv():
    if "email" not in session: return redirect(url_for("login"))
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Date","Mood","Sleep","Note"])
    with get_db() as con:
        for r in con.execute("SELECT * FROM moods WHERE user_email=?", (session["email"],)):
            w.writerow([r["ts"], r["mood"], r["sleep"], r["note"]])
    data = io.BytesIO(buf.getvalue().encode()); data.seek(0)
    return send_file(data, as_attachment=True, download_name="selfos.csv", mimetype="text/csv")

@app.route("/export_pdf")
def export_pdf():
    if "email" not in session: return redirect(url_for("login"))
    buf = io.BytesIO(); pdf = canvas.Canvas(buf, pagesize=letter)
    pdf.drawString(50, 750, f"SelfOS Report — {session['email']}")
    y = 720
    with get_db() as con:
        for r in con.execute("SELECT * FROM moods WHERE user_email=?", (session["email"],)):
            pdf.drawString(50, y, f"{r['ts']} | Mood {r['mood']} | Sleep {r['sleep']}h | {r['note'] or ''}")
            y -= 15
            if y < 60: pdf.showPage(); y = 750
    pdf.save(); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="selfos.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True)
