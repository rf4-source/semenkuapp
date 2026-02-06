# ================= IMPORT =================
import os
import io
import time
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
from rapidfuzz import fuzz
from cryptography.fernet import Fernet
from streamlit_cookies_manager import EncryptedCookieManager


# ================= PAGE CONFIG (HARUS PALING ATAS, 1x SAJA) =================
st.set_page_config(
    page_title="MIS Historis Search",
    layout="wide"
)


# ================= CONFIG AUTH =================
APP_PASSWORD = st.secrets["APP_PASSWORD"]
COOKIE_SECRET_KEY = st.secrets["COOKIE_SECRET_KEY"]

MAX_ATTEMPTS = 5
LOCK_DURATION = timedelta(hours=1)
COOKIE_EXPIRE_HOURS = 1


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
        cookies.pop("logged_in", None)
        cookies.pop("login_time", None)
        cookies.save()
        expired = True


# ================= LOGIN STATUS =================
is_logged_in = cookies.get("logged_in") == "true"


# ================= LOGIN PAGE =================
if not is_logged_in:
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
            cookies["logged_in"] = "true"
            cookies["login_time"] = datetime.now().isoformat()
            cookies.save()

            st.session_state.attempts = 0
            st.session_state.locked_until = None

            st.success("✅ Login berhasil")
            time.sleep(0.3)
            st.rerun()
        else:
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

    st.stop()  # ⛔ STOP DI LOGIN PAGE


# ================= MAIN APP =================
st.title("🔎 MIS Historis – Bill of Material")
st.caption("Sumber data: encrypted dataset")


# ================= DATA CONFIG =================
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


# ================= LOAD DATA (CACHE + ENCRYPT) =================
@st.cache_data(show_spinner=True)
def load_data(enc_mtime: float) -> pd.DataFrame:
    key = st.secrets["PARQUET_KEY"].encode()
    f = Fernet(key)

    with open(ENC_PATH, "rb") as f_enc:
        decrypted_bytes = f.decrypt(f_enc.read())

    df = pd.read_parquet(
        io.BytesIO(decrypted_bytes),
        engine="pyarrow"
    )
    df["Doc Date"] = pd.to_datetime(df["Doc Date"], errors="coerce")
    return df


df = load_data(os.path.getmtime(ENC_PATH))


# ================= SEARCH HELPERS =================
def build_search_mask(series: pd.Series, query: str) -> pd.Series:
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
    series = series.astype(str)

    def match(val: str) -> bool:
        return fuzz.partial_ratio(query.lower(), val.lower()) >= threshold

    return series.apply(match)


# ================= SIDEBAR =================
st.sidebar.divider()
if st.sidebar.button("🚪 Logout"):
    cookies.pop("logged_in", None)
    cookies.pop("login_time", None)
    cookies.save()
    st.rerun()

st.sidebar.header("🔧 Filter")

search_remark = st.sidebar.text_input("Remark")
search_name = st.sidebar.text_input("Name & Specification")
search_code = st.sidebar.text_input("Code Number")

st.sidebar.subheader("⚙️ Fuzzy Search")

use_fuzzy_name = st.sidebar.checkbox("Fuzzy Name & Spec")
fuzzy_name_threshold = st.sidebar.slider("Sensitivity Name", 60, 90, 75, 5)

use_fuzzy_remark = st.sidebar.checkbox("Fuzzy Remark")
fuzzy_remark_threshold = st.sidebar.slider("Sensitivity Remark", 60, 90, 70, 5)

plant = st.sidebar.multiselect(
    "Used For Plant",
    sorted(df["Used For"].dropna().unique())
)

cost_center = st.sidebar.multiselect(
    "Cost Center",
    sorted(df["Cost Center"].dropna().unique())
)

approval = st.sidebar.multiselect(
    "Approval Status",
    sorted(df["ApprovalStat"].dropna().unique())
)


# ================= FILTER LOGIC =================
filtered = df.copy()

if search_code:
    filtered = filtered[build_search_mask(filtered["Code Number"], search_code)]

if search_name:
    filtered = filtered[
        build_fuzzy_mask(filtered["Name and Specification"], search_name, fuzzy_name_threshold)
        if use_fuzzy_name else
        build_search_mask(filtered["Name and Specification"], search_name)
    ]

if search_remark:
    filtered = filtered[
        build_fuzzy_mask(filtered["Remark"], search_remark, fuzzy_remark_threshold)
        if use_fuzzy_remark else
        build_search_mask(filtered["Remark"], search_remark)
    ]

if plant:
    filtered = filtered[filtered["Used For"].isin(plant)]

if cost_center:
    filtered = filtered[filtered["Cost Center"].isin(cost_center)]

if approval:
    filtered = filtered[filtered["ApprovalStat"].isin(approval)]


# ================= PAGINATION =================
PAGE_SIZE = 100
total_rows = len(filtered)
total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

page = st.number_input("📄 Halaman", 1, total_pages, 1)
start = (page - 1) * PAGE_SIZE
end = start + PAGE_SIZE

page_df = filtered.iloc[start:end]


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
        st.metric("Jumlah Dokumen", filtered["Doc Number"].nunique())

    with c2:
        st.metric("Jumlah Item", len(filtered))

    with c3:
        st.metric("Total Qty", int(filtered["QTY Requested"].sum()))

    with c4:
        st.metric("Total Value", f"Rp {filtered['Price Total'].sum():,.0f}")
