import streamlit as st
import pandas as pd
from rapidfuzz import fuzz
import os
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

from streamlit_cookies_manager import EncryptedCookieManager
import time

# ================= CONFIG =================
APP_PASSWORD = "Palimanan2026!"
MAX_ATTEMPTS = 5
LOCK_DURATION = timedelta(hours=1)
COOKIE_EXPIRE_HOURS = 1

COOKIE_SECRET_KEY = "s1per-secget-k3y-123"   # JANGAN diganti setelah live

# ================= COOKIE MANAGER =================
cookies = EncryptedCookieManager(
    prefix="mis_auth_",
    password=COOKIE_SECRET_KEY
)

if not cookies.ready():
    st.stop()

# ================= SESSION INIT =================
if "attempts" not in st.session_state:
    st.session_state.attempts = 0

if "locked_until" not in st.session_state:
    st.session_state.locked_until = None

# ================= COOKIE EXPIRY CHECK =================
expired = False

if cookies.get("login_time"):
    try:
        login_time = datetime.fromisoformat(cookies.get("login_time"))
        if datetime.now() - login_time > timedelta(hours=COOKIE_EXPIRE_HOURS):
            cookies.pop("logged_in", None)
            cookies.pop("login_time", None)
            cookies.save()
            expired = True
    except Exception:
        # kalau format cookie rusak
        cookies.pop("logged_in", None)
        cookies.pop("login_time", None)
        cookies.save()
        expired = True

# ================= LOGIN STATUS =================
is_logged_in = cookies.get("logged_in") == "true"

# ================= LOGIN PAGE =================
if not is_logged_in:
    st.set_page_config(page_title="Login MIS Historis", layout="centered")
    st.title("🔐 Login Akses MIS Historis")

    if expired:
        st.warning("⏰ Session login habis, silakan login ulang")

    now = datetime.now()

    # ---- LOCK CHECK
    if st.session_state.locked_until and now < st.session_state.locked_until:
        remaining = st.session_state.locked_until - now
        minutes = int(remaining.total_seconds() // 60) + 1

        st.error(
            f"🚫 Terlalu banyak percobaan gagal.\n\n"
            f"Tunggu **{minutes} menit** sebelum mencoba lagi."
        )
        st.stop()

    pwd = st.text_input(
        "Masukkan Password",
        type="password",
        placeholder="Password akses internal"
    )

    if st.button("Login"):
        if pwd == APP_PASSWORD:
            # ✅ LOGIN SUKSES
            cookies["logged_in"] = "true"
            cookies["login_time"] = datetime.now().isoformat()
            cookies.save()

            st.session_state.attempts = 0
            st.session_state.locked_until = None

            st.success("✅ Login berhasil")
            time.sleep(0.3)
            st.rerun()

        else:
            # ❌ LOGIN GAGAL
            st.session_state.attempts += 1
            remaining = MAX_ATTEMPTS - st.session_state.attempts

            if remaining <= 0:
                st.session_state.locked_until = now + LOCK_DURATION
                st.error(
                    "🚫 Password salah 5 kali.\n\n"
                    "Akses dikunci selama **1 jam**."
                )
                st.stop()
            else:
                st.warning(
                    f"❌ Password salah.\n\n"
                    f"Sisa percobaan: **{remaining} kali**"
                )

    st.stop()   # ⛔ STOP DI SINI SAJA (PENTING)

# ================== END AUTH ==================
# ⬇⬇⬇ KODE APP UTAMA KAMU DITULIS DI BAWAH INI ⬇⬇⬇



# ================= CONFIG =================
# ================= CONFIG =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENC_PATH = os.path.join(BASE_DIR, "mis_list.enc")

COLUMNS_CORE = [
    "Doc Number",
    "Doc Date",
    "Code Number",
    "Name and Specification",
    "Remark",
    "QTY Requested",
    "UOM",
    "Price per UoM",
    "Price Total",
    "Used For",
    "Cost Center",
    "Dept/Section",
    "ApprovalStat",
]

# ================= PAGE =================
st.set_page_config(
    page_title="MIS Historis Search",
    layout="wide"
)
st.title("🔎 MIS Historis – Bill of Material")
st.caption("Sumber data: encrypted dataset")

# ================= LOAD DATA (FAST + AMAN) =================
@st.cache_data(show_spinner=True)
def load_data(enc_mtime):
    key = st.secrets["PARQUET_KEY"].encode()
    f = Fernet(key)

    with open(ENC_PATH, "rb") as f_enc:
        decrypted_bytes = f.decrypt(f_enc.read())

    df = pd.read_parquet(io.BytesIO(decrypted_bytes))
    df["Doc Date"] = pd.to_datetime(df["Doc Date"], errors="coerce")
    return df

df = load_data(os.path.getmtime(ENC_PATH))

# ================= SEARCH HELPERS =================
def build_search_mask(series: pd.Series, query: str) -> pd.Series:
    """
    Exact search (case-insensitive)
    - a&b  → AND
    - a+b  → OR
    - a    → contains
    """
    series = series.astype(str)

    if "&" in query:
        parts = [p.strip() for p in query.split("&") if p.strip()]
        mask = series.str.contains(parts[0], case=False, na=False)
        for p in parts[1:]:
            mask &= series.str.contains(p, case=False, na=False)
        return mask

    if "+" in query:
        parts = [p.strip() for p in query.split("+") if p.strip()]
        mask = series.str.contains(parts[0], case=False, na=False)
        for p in parts[1:]:
            mask |= series.str.contains(p, case=False, na=False)
        return mask

    return series.str.contains(query, case=False, na=False)


def build_fuzzy_mask(series: pd.Series, query: str, threshold: int) -> pd.Series:
    """
    Fuzzy search (typo tolerant, Elastic-like)
    """
    series = series.astype(str)

    def match(val: str) -> bool:
        return fuzz.partial_ratio(
            query.lower(),
            val.lower()
        ) >= threshold

    return series.apply(match)

# ================= SIDEBAR =================
st.sidebar.divider()
if st.sidebar.button("🚪 Logout"):
    cookies.pop("logged_in", None)
    cookies.pop("login_time", None)
    cookies.save()
    st.rerun()


st.sidebar.header("🔧 Filter")

# ---- Text search
st.sidebar.subheader("🔍 Pencarian Teks")

search_remark = st.sidebar.text_input(
    "Remark",
    placeholder="ex: MJ-12&ganti  |  MJ2-10+J-15C"
)

search_name = st.sidebar.text_input(
    "Name & Specification",
    placeholder="contoh: chain&rs  |  bearing+brg"
)

search_code = st.sidebar.text_input(
    "Code Number",
    placeholder="contoh: 31-0100"
)

# ---- Fuzzy options (TERPISAH)
st.sidebar.subheader("⚙️ Fuzzy Search (Typo Tolerant)")

use_fuzzy_name = st.sidebar.checkbox(
    "Fuzzy Name & Specification",
    value=False
)

fuzzy_name_threshold = st.sidebar.slider(
    "Sensitivity Name & Spec",
    min_value=60,
    max_value=90,
    value=75,
    step=5
)

use_fuzzy_remark = st.sidebar.checkbox(
    "Fuzzy Remark",
    value=False
)

fuzzy_remark_threshold = st.sidebar.slider(
    "Sensitivity Remark",
    min_value=60,
    max_value=90,
    value=70,
    step=5
)

# ---- Other filters
st.sidebar.subheader("📂 Filter Data")

plant = st.sidebar.multiselect(
    "Used For Plant",
    options=sorted(df["Used For"].dropna().unique())
)

costCenter = st.sidebar.multiselect(
    "Cost Center",
    options=sorted(df["Cost Center"].dropna().unique())
)

approval = st.sidebar.multiselect(
    "Approval Status",
    options=sorted(df["ApprovalStat"].dropna().unique())
)

min_date = df["Doc Date"].min()
max_date = df["Doc Date"].max()
#date_range = st.sidebar.date_input(
#    "Range Doc Date",
#    value=(min_date, max_date)
#)
date_range = st.sidebar.date_input(
    "Range Doc Date",
    value=None
)
# ================= FILTER LOGIC =================
filtered = df.copy()

# Code Number → exact
if search_code:
    filtered = filtered[
        build_search_mask(filtered["Code Number"], search_code)
    ]

# Name & Spec → exact / fuzzy
if search_name:
    if use_fuzzy_name:
        filtered = filtered[
            build_fuzzy_mask(
                filtered["Name and Specification"],
                search_name,
                fuzzy_name_threshold
            )
        ]
    else:
        filtered = filtered[
            build_search_mask(
                filtered["Name and Specification"],
                search_name
            )
        ]

# Remark → exact / fuzzy
if search_remark:
    if use_fuzzy_remark:
        filtered = filtered[
            build_fuzzy_mask(
                filtered["Remark"],
                search_remark,
                fuzzy_remark_threshold
            )
        ]
    else:
        filtered = filtered[
            build_search_mask(
                filtered["Remark"],
                search_remark
            )
        ]

# Other filters
if plant:
    filtered = filtered[filtered["Used For"].isin(plant)]

if costCenter:
    filtered = filtered[filtered["Cost Center"].isin(costCenter)]

if approval:
    filtered = filtered[filtered["ApprovalStat"].isin(approval)]

#if date_range and len(date_range) == 2:
#    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
#    filtered = filtered[
#        (filtered["Doc Date"] >= start) &
#        (filtered["Doc Date"] <= end)
#    ]

if date_range and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    filtered = filtered[
        (filtered["Doc Date"] >= start) &
        (filtered["Doc Date"] <= end)
    ]

# ================= PAGINATION =================
PAGE_SIZE = 100

total_rows = len(filtered)
total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

page = st.number_input(
    "📄 Halaman",
    min_value=1,
    max_value=total_pages,
    value=1,
    step=1
)

start_idx = (page - 1) * PAGE_SIZE
end_idx = start_idx + PAGE_SIZE

page_df = filtered.iloc[start_idx:end_idx]


# ================= OUTPUT =================
st.subheader(
    f"📋 Hasil Pencarian "
    f"({total_rows:,} baris | halaman {page}/{total_pages})"
)

st.dataframe(
    page_df[COLUMNS_CORE],
    use_container_width=True,
    hide_index=True
)

# ================= SUMMARY =================
if not filtered.empty:
    st.divider()
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Jumlah MIS", filtered["MIS No."].nunique())

    with c2:
        st.metric("Jumlah Item", len(filtered))

    with c3:
        st.metric("Total Qty", int(filtered["QTY Requested"].sum()))

    with c4:
        st.metric(
            "Total Value",
            f"Rp {filtered['Price Total'].sum():,.0f}"
        )


