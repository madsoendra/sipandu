# dashboard.py (Versi Final)

import streamlit as st
import pandas as pd
import joblib
import numpy as np
import sqlite3
from datetime import datetime
from io import BytesIO
import google.generativeai as genai

# --- 1. Pengaturan Halaman dan Konfigurasi Awal ---
st.set_page_config(
    page_title="SI PANDU AI - MAN 3 Medan",
    page_icon="🎓",
    layout="wide"
)
NAMA_FILE_DB = 'siswa.db'

# --- 2. Konfigurasi & Fungsi-fungsi Inti ---

# Konfigurasi Google Generative AI
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model_genai = genai.GenerativeModel('gemini-1.5-flash')
    AI_ENABLED = True
except Exception:
    AI_ENABLED = False

### --- FUNGSI BARU: Pemeriksaan Password --- ###
def check_password():
    """Mengembalikan True jika pengguna telah memasukkan password yang benar."""
    
    # Inisialisasi session state untuk status login
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    # Jika sudah login, langsung kembalikan True
    if st.session_state["password_correct"]:
        return True

    # Tampilkan form login jika belum login
    st.title("🔒 Login Akses SI PANDU AI")
    st.write("Silakan masukkan password untuk mengakses dasbor.")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            st.rerun() # Muat ulang halaman setelah login berhasil
        else:
            st.error("Password yang Anda masukkan salah.")
    
    return False

@st.cache_resource
def load_models():
    """Memuat model prediksi, scaler, dan daftar kolom dari file."""
    try:
        model = joblib.load('model_prediksi.pkl')
        scaler = joblib.load('scaler.pkl')
        model_columns = joblib.load('model_columns.pkl')
        return model, scaler, model_columns
    except FileNotFoundError:
        return None, None, None

def get_connection():
    """Membuat koneksi ke database SQLite."""
    return sqlite3.connect(NAMA_FILE_DB, check_same_thread=False)

def init_db():
    """Memastikan semua tabel yang dibutuhkan ada di database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS data_siswa (Nama_Siswa TEXT, NISN TEXT PRIMARY KEY, Kelas TEXT, Nilai_Rata_Rata_Semester REAL, Jumlah_Absensi INTEGER, Status_Beasiswa TEXT, Pekerjaan_Orang_Tua TEXT, Riwayat_Pelanggaran INTEGER)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS log_intervensi (id INTEGER PRIMARY KEY AUTOINCREMENT, nisn TEXT NOT NULL, tanggal TEXT NOT NULL, tindakan TEXT NOT NULL, catatan TEXT, dicatat_oleh TEXT, FOREIGN KEY (nisn) REFERENCES data_siswa(NISN))""")
    conn.commit()
    conn.close()

def read_data(conn, query='SELECT * FROM data_siswa'):
    """Membaca data siswa dari database."""
    return pd.read_sql(query, conn)

def update_data(conn, df_edited):
    """Menyimpan DataFrame yang sudah diedit ke database."""
    df_edited.to_sql('data_siswa', conn, if_exists='replace', index=False)

def add_data(conn, data_baru):
    """Menambahkan siswa baru ke database."""
    query = "INSERT INTO data_siswa (Nama_Siswa, NISN, Kelas, Nilai_Rata_Rata_Semester, Jumlah_Absensi, Status_Beasiswa, Pekerjaan_Orang_Tua, Riwayat_Pelanggaran) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    cursor = conn.cursor()
    cursor.execute(query, tuple(data_baru.values()))
    conn.commit()

def delete_data(conn, nisn_list):
    """Menghapus siswa dari database berdasarkan NISN."""
    query = "DELETE FROM data_siswa WHERE NISN IN ({seq})".format(seq=','.join(['?']*len(nisn_list)))
    cursor = conn.cursor()
    cursor.execute(query, nisn_list)
    conn.commit()

def add_log_intervensi(conn, log_data):
    """Menambahkan catatan log intervensi baru."""
    query = "INSERT INTO log_intervensi (nisn, tanggal, tindakan, catatan, dicatat_oleh) VALUES (?, ?, ?, ?, ?)"
    cursor = conn.cursor()
    cursor.execute(query, tuple(log_data.values()))
    conn.commit()

def read_log_intervensi(conn, nisn):
    """Membaca riwayat log intervensi untuk seorang siswa."""
    return pd.read_sql("SELECT id, tanggal, tindakan, catatan, dicatat_oleh FROM log_intervensi WHERE nisn = ? ORDER BY tanggal DESC", conn, params=(nisn,))

def delete_log_intervensi(conn, log_id):
    """Menghapus satu catatan log intervensi berdasarkan ID uniknya."""
    query = "DELETE FROM log_intervensi WHERE id = ?"
    cursor = conn.cursor()
    cursor.execute(query, (log_id,))
    conn.commit()

@st.cache_data
def convert_df_to_excel(df):
    """Mengonversi DataFrame ke format file Excel untuk di-download."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Laporan Risiko Siswa')
    return output.getvalue()

def generate_ai_recommendations(student_details, student_risk, key_factors):
    """Membuat prompt dan memanggil AI untuk rekomendasi intervensi."""
    prompt = f"""TUGAS: Berdasarkan data siswa berikut, berikan rekomendasi intervensi yang konkret, personal, dan bisa ditindaklanjuti. Pisahkan dengan jelas rekomendasi untuk **Wali Kelas** dan **Guru BK**. DATA SISWA: - Nama: {student_details['Nama_Siswa']} - Kelas: {student_details['Kelas']} - Tingkat Risiko Prediksi: {student_risk['Tingkat Risiko (%)']:.2f}% - Faktor Risiko Utama yang Teridentifikasi: {', '.join(key_factors)} - Detail Data: Nilai Rata-Rata={student_details['Nilai_Rata_Rata_Semester']}, Jumlah Absensi={student_details['Jumlah_Absensi']} hari, Poin Pelanggaran={student_details['Riwayat_Pelanggaran']}, Pekerjaan Ortu={student_details['Pekerjaan_Orang_Tua']}. KONTEKS PERAN: Anda adalah seorang konselor sekolah dan psikolog pendidikan yang sangat berpengalaman. Gunakan bahasa yang empatik, profesional, dan positif. Format jawaban dalam bentuk poin-poin markdown."""
    try:
        response = model_genai.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Terjadi kesalahan saat menghubungi AI: {e}"

def analyze_intervention_logs(logs_df, student_name):
    """Membuat prompt dan memanggil AI untuk analisis log intervensi."""
    log_string = logs_df.to_string(index=False)
    prompt = f"""TUGAS: Berdasarkan riwayat log intervensi berikut, berikan analisis singkat dalam 3 bagian: 1. Rangkuman Kondisi Siswa, 2. Identifikasi Tema/Pola, 3. Saran Fokus Intervensi Selanjutnya. RIWAYAT LOG INTERVENSI UNTUK SISWA BERNAMA {student_name}:\n{log_string}\n\nKONTEKS PERAN: Anda adalah seorang psikolog pendidikan senior. Gunakan bahasa yang profesional, to-the-point, dan format jawaban dalam bentuk markdown."""
    try:
        response = model_genai.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Terjadi kesalahan saat menghubungi AI: {e}"

# --- 5. EKSEKUSI UTAMA APLIKASI ---
def main():
    """Fungsi utama untuk menjalankan seluruh alur aplikasi Streamlit."""
    
    # Inisialisasi dan Muat Aset
    init_db() 
    model, scaler, model_columns = load_models()
    conn = get_connection()

    if model is None:
        st.error("File model tidak ditemukan! Harap jalankan skrip '2_latih_model.py' terlebih dahulu.")
        st.stop()

    # --- Render Sidebar ---
    with st.sidebar:
        try:
            st.image("https://man3medan.sch.id/wp-content/uploads/2023/11/MAN-3-Kota-Medan-1.png", width=200)
        except Exception:
            st.write("Logo MAN 3 Medan") # Fallback jika gambar tidak bisa di-load
            
        st.title("🎓 SI PANDU - AI")
        st.write("Sistem Peringatan Dini dan Dukungan Siswa")
        if not AI_ENABLED:
            st.warning("Fitur AI nonaktif. Periksa API Key di .streamlit/secrets.toml")
        
        st.divider()
        
        with st.expander("Mode Simulasi Individual"):
            nilai = st.slider('Nilai Rata-Rata Semester', 0.0, 100.0, 75.5, 0.5)
            absensi = st.slider('Jumlah Absensi', 0, 30, 5)
            beasiswa = st.selectbox('Menerima Beasiswa?', ('Ya', 'Tidak'), key='beasiswa_sidebar')
            pekerjaan = st.selectbox('Pekerjaan Orang Tua', ('PNS', 'Wiraswasta', 'Buruh', 'Petani', 'Lainnya'), key='pekerjaan_sidebar')
            pelanggaran = st.slider('Total Poin Pelanggaran', 0, 100, 10)
            if st.button('Jalankan Simulasi Risiko'):
                data_simulasi = {'Nilai_Rata_Rata_Semester': nilai, 'Jumlah_Absensi': absensi, 'Status_Beasiswa': 1 if beasiswa == 'Ya' else 0, 'Riwayat_Pelanggaran': pelanggaran, 'Pekerjaan_Orang_Tua_Buruh': 1 if pekerjaan == 'Buruh' else 0, 'Pekerjaan_Orang_Tua_Lainnya': 1 if pekerjaan == 'Lainnya' else 0, 'Pekerjaan_Orang_Tua_PNS': 1 if pekerjaan == 'PNS' else 0, 'Pekerjaan_Orang_Tua_Petani': 1 if pekerjaan == 'Petani' else 0, 'Pekerjaan_Orang_Tua_Wiraswasta': 1 if pekerjaan == 'Wiraswasta' else 0}
                df_simulasi = pd.DataFrame(data_simulasi, index=[0])[model_columns]
                scaled_simulasi = scaler.transform(df_simulasi)
                pred_proba_simulasi = model.predict_proba(scaled_simulasi)
                risk_score_simulasi = pred_proba_simulasi[0][1] * 100
                st.subheader("Hasil Simulasi")
                if risk_score_simulasi >= 75: st.error('**TINGKAT TINGGI / PRIORITAS UTAMA** 🔴')
                elif risk_score_simulasi >= 50: st.warning('**PERHATIAN KHUSUS** 🟠')
                elif risk_score_simulasi >= 25: st.info('**TINGKAT WASPADA** 🟡')
                else: st.success('**TINGKAT AMAN** 🟢')
                st.metric(label="Tingkat Keyakinan Risiko", value=f"{risk_score_simulasi:.2f}%")
        st.divider()
        st.info("Aplikasi ini dikembangkan untuk SOBAT Competition 2025.")

    # --- Render Tampilan Utama dengan Tabs ---
    st.title("Sistem Prediksi dan Intervensi Siswa MAN 3 Medan")
    
    df_siswa = read_data(conn)
    if not df_siswa.empty:
        df_identitas = df_siswa[['Nama_Siswa', 'NISN', 'Kelas']].copy()
        df_features_raw = df_siswa.drop(columns=['Nama_Siswa', 'NISN', 'Kelas'])
        df_features = df_features_raw.copy()
        df_features['Status_Beasiswa'] = df_features['Status_Beasiswa'].map({'Ya': 1, 'Tidak': 0})
        df_features = pd.get_dummies(df_features, columns=['Pekerjaan_Orang_Tua'])
        for col in model_columns:
            if col not in df_features.columns: df_features[col] = 0
        df_features = df_features[model_columns]
        scaled_features = scaler.transform(df_features)
        prediction_proba = model.predict_proba(scaled_features)
        risk_scores = prediction_proba[:, 1] * 100
        df_hasil = df_identitas
        df_hasil['Tingkat Risiko (%)'] = risk_scores
        df_hasil_sorted = df_hasil.sort_values(by='Tingkat Risiko (%)', ascending=False).reset_index(drop=True)
        df_hasil_sorted.index = df_hasil_sorted.index + 1
    else:
        df_hasil_sorted = pd.DataFrame()

    tab_prediksi, tab_analitik, tab_admin = st.tabs(["📊 Dasbor Prediksi Risiko", "📈 Dasbor Analitik Sekolah", "⚙️ Manajemen Data & Intervensi"])

    with tab_prediksi:
        st.header("Laporan Prediksi Risiko Putus Sekolah")
        if df_hasil_sorted.empty:
            st.warning("Database siswa kosong. Silakan tambahkan data di tab 'Manajemen Data & Intervensi'.")
        else:
            excel_file = convert_df_to_excel(df_hasil_sorted)
            st.download_button(label="📥 Download Laporan sebagai Excel", data=excel_file, file_name=f"laporan_risiko_siswa_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.dataframe(df_hasil_sorted.style.background_gradient(cmap='Reds', subset=['Tingkat Risiko (%)']).format({'Tingkat Risiko (%)': "{:.2f}%"}), use_container_width=True)
            st.divider()
            st.subheader("Detail Analisis & Log Intervensi per Siswa")
            selected_student_name = st.selectbox('Pilih siswa:', options=df_hasil_sorted['Nama_Siswa'])
            if selected_student_name:
                student_details = df_siswa[df_siswa['Nama_Siswa'] == selected_student_name].iloc[0]
                student_risk = df_hasil[df_hasil['Nama_Siswa'] == selected_student_name].iloc[0]
                key_factors = []
                if student_details['Jumlah_Absensi'] > 12: key_factors.append("Tingkat Absensi Tinggi")
                if student_details['Nilai_Rata_Rata_Semester'] < 70: key_factors.append("Penurunan Nilai Akademik")
                if student_details['Riwayat_Pelanggaran'] > 30: key_factors.append("Masalah Perilaku/Disiplin")
                if not key_factors: key_factors.append("Tidak ada faktor risiko menonjol")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader(f"Profil: {student_details['Nama_Siswa']}")
                    st.markdown(f"**NISN:** {student_details['NISN']} | **Kelas:** {student_details['Kelas']}")
                    st.metric(label="Tingkat Prediksi Risiko", value=f"{student_risk['Tingkat Risiko (%)']:.2f}%")
                    st.divider()
                    st.subheader("Data Sumber"); st.markdown(f"""- **Nilai Rata-Rata:** `{student_details['Nilai_Rata_Rata_Semester']}`\n- **Jumlah Absensi:** `{student_details['Jumlah_Absensi']}` hari\n- **Poin Pelanggaran:** `{student_details['Riwayat_Pelanggaran']}` poin\n- **Beasiswa:** `{student_details['Status_Beasiswa']}`\n- **Pekerjaan Ortu:** `{student_details['Pekerjaan_Orang_Tua']}`""")
                    st.divider()
                    st.subheader("Faktor Risiko Utama"); 
                    for factor in key_factors: st.error(f"- {factor}")
                    st.divider()
                    st.subheader("Grafik Tren Risiko (Contoh)")
                    chart_data = pd.DataFrame(np.random.randn(5, 1) * 10 + student_risk['Tingkat Risiko (%)'], index=['Bulan 1', 'Bulan 2', 'Bulan 3', 'Bulan 4', 'Bulan 5'], columns=['Tingkat Risiko']).clip(0, 100)
                    st.line_chart(chart_data)
                    
                    
                with col2:
                    st.subheader("Rekomendasi")
                    if st.button("💡 Dapatkan Rekomendasi Intervensi berdasarkan Sumber Data", key=f"rekomendasi_ai_{student_details['NISN']}", disabled=not AI_ENABLED):
                        with st.spinner("Asisten AI sedang berpikir..."):
                            rekomendasi = generate_ai_recommendations(student_details, student_risk, key_factors)
                            st.markdown(rekomendasi)
                    st.divider()
                    st.subheader("📝 Log Intervensi & Pelacakan Progres")
                    with st.expander("Catat / Hapus Intervensi"):
                        with st.form("form_log", clear_on_submit=True):
                            st.write("**Catat Intervensi Baru**")
                            nama_guru = st.text_input("Dicatat oleh (Nama Guru)")
                            tindakan = st.selectbox("Jenis Tindakan", ["Konseling Individual", "Panggilan Orang Tua", "Bimbingan Belajar", "Kunjungan Rumah", "Lainnya"])
                            catatan = st.text_area("Catatan Detail")
                            if st.form_submit_button("Simpan Log"):
                                if catatan and nama_guru:
                                    log_data = {'nisn': student_details['NISN'], 'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M'), 'tindakan': tindakan, 'catatan': catatan, 'dicatat_oleh': nama_guru}
                                    add_log_intervensi(conn, log_data); st.success("Log intervensi berhasil disimpan!"); st.rerun() 
                                else:
                                    st.warning("Nama Guru dan Catatan Detail tidak boleh kosong.")
                        
                        df_log_check = read_log_intervensi(conn, student_details['NISN'])
                        if not df_log_check.empty:
                            st.divider()
                            st.write("**Hapus Catatan Intervensi**")
                            log_options = {row['id']: f"{row['tanggal']} - {row['tindakan']} (oleh {row['dicatat_oleh']})" for index, row in df_log_check.iterrows()}
                            selected_log_id = st.selectbox("Pilih catatan untuk dihapus:", options=log_options.keys(), format_func=lambda x: log_options[x])
                            if st.button("Hapus Catatan Terpilih", type="primary"):
                                delete_log_intervensi(conn, selected_log_id); st.success("Catatan berhasil dihapus!"); st.rerun()
                    
                    df_log_display = read_log_intervensi(conn, student_details['NISN'])
                    if not df_log_display.empty:
                        st.write("Riwayat Intervensi yang Sudah Tercatat:")
                        st.dataframe(df_log_display.drop(columns=['id']), use_container_width=True)
                        if st.button("🧠 Analisis Catatan Intervensi", key=f"analisis_ai_{student_details['NISN']}", disabled=not AI_ENABLED):
                            with st.spinner("AI sedang menganalisis catatan..."):
                                analisis_log = analyze_intervention_logs(df_log_display.drop(columns=['id']), selected_student_name)
                                st.markdown(analisis_log)
                    else:
                        st.info("Belum ada riwayat intervensi untuk siswa ini.")

    with tab_analitik:
        st.header("Analitik Risiko Siswa Tingkat Sekolah")
        if df_hasil_sorted.empty:
            st.warning("Database siswa kosong.")
        else:
            df_berisiko = df_hasil_sorted[df_hasil_sorted['Tingkat Risiko (%)'] >= 70]
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Siswa", len(df_hasil_sorted))
            col2.metric("Siswa Berisiko Tinggi (>70%)", len(df_berisiko), f"{len(df_berisiko)/len(df_hasil_sorted):.1%}")
            col3.metric("Rata-rata Risiko Sekolah", f"{df_hasil_sorted['Tingkat Risiko (%)'].mean():.2f}%")
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Rata-rata Risiko per Kelas")
                # Gabungkan df_siswa dengan df_hasil_sorted untuk mendapatkan kelas dan risiko bersamaan
                df_merged_risk = df_siswa.merge(df_hasil_sorted[['NISN', 'Tingkat Risiko (%)']], on="NISN")
                risiko_per_kelas = df_merged_risk.groupby('Kelas')['Tingkat Risiko (%)'].mean().sort_values(ascending=False)
                st.bar_chart(risiko_per_kelas)
            with col2:
                st.subheader("Distribusi Faktor Risiko Utama")
                if not df_berisiko.empty:
                    faktor_counts = {}
                    df_siswa_berisiko = df_siswa[df_siswa['NISN'].isin(df_berisiko['NISN'])]
                    faktor_counts['Absensi Tinggi'] = len(df_siswa_berisiko[df_siswa_berisiko['Jumlah_Absensi'] > 12])
                    faktor_counts['Akademik Rendah'] = len(df_siswa_berisiko[df_siswa_berisiko['Nilai_Rata_Rata_Semester'] < 70])
                    faktor_counts['Masalah Disiplin'] = len(df_siswa_berisiko[df_siswa_berisiko['Riwayat_Pelanggaran'] > 30])
                    df_faktor = pd.DataFrame(list(faktor_counts.items()), columns=['Faktor', 'Jumlah Siswa'])
                    st.bar_chart(df_faktor.set_index('Faktor'))
                else:
                    st.info("Tidak ada siswa dalam kategori berisiko tinggi saat ini.")

    with tab_admin:
        st.header("Manajemen Database Siswa")
        df_admin = read_data(conn)
        with st.expander("➕ Tambah Siswa Baru"):
            with st.form("form_tambah_siswa", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                with col1: nama_baru = st.text_input("Nama Siswa", placeholder="Budi Santoso"); nisn_baru = st.text_input("NISN", placeholder="1234567890"); kelas_baru = st.text_input("Kelas", placeholder="XI MIPA 3")
                with col2: nilai_baru = st.number_input("Nilai Rata-Rata Semester", min_value=0.0, max_value=100.0, value=75.0); absensi_baru = st.number_input("Jumlah Absensi", min_value=0, value=0); pelanggaran_baru = st.number_input("Riwayat Pelanggaran", min_value=0, value=0)
                with col3: beasiswa_baru = st.selectbox("Status Beasiswa", ["Tidak", "Ya"], key="beasiswa_admin"); pekerjaan_baru = st.selectbox("Pekerjaan Orang Tua", ['PNS', 'Wiraswasta', 'Buruh', 'Petani', 'Lainnya'], key="pekerjaan_admin")
                if st.form_submit_button("Tambah Siswa"):
                    data_baru = {'Nama_Siswa': nama_baru, 'NISN': nisn_baru, 'Kelas': kelas_baru, 'Nilai_Rata_Rata_Semester': nilai_baru, 'Jumlah_Absensi': absensi_baru, 'Status_Beasiswa': beasiswa_baru, 'Pekerjaan_Orang_Tua': pekerjaan_baru, 'Riwayat_Pelanggaran': pelanggaran_baru}
                    add_data(conn, data_baru)
                    st.rerun()
        st.divider()
        st.subheader("✏️ Edit atau Hapus Data Siswa")
        st.info("Gunakan tabel di bawah untuk mengedit data secara langsung. Klik 'Simpan Perubahan' setelah selesai.")
        df_edited = st.data_editor(df_admin, num_rows="dynamic", use_container_width=True, key="data_editor")
        if st.button("Simpan Perubahan"):
            update_data(conn, df_edited)
            st.rerun()
        with st.expander("❌ Hapus Siswa"):
            options_dict = dict(zip(df_admin['NISN'], df_admin['Nama_Siswa'] + " (" + df_admin['NISN'].astype(str) + ")"))
            nisn_untuk_dihapus = st.multiselect("Pilih siswa untuk dihapus:", options=options_dict.keys(), format_func=lambda x: options_dict[x])
            if st.button("Hapus Siswa Terpilih", type="primary"):
                if nisn_untuk_dihapus:
                    delete_data(conn, nisn_untuk_dihapus)
                    st.rerun()
                else:
                    st.warning("Silakan pilih minimal satu siswa untuk dihapus.")

    conn.close()

### --- PERBAIKAN: "Bungkus" Aplikasi Utama dengan Pemeriksaan Password --- ###
if check_password():
    # Jika password benar, jalankan seluruh aplikasi utama

# if __name__ == "__main__":
    main()