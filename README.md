# Şagird statistikası Dashboard (Streamlit)

123 №-li məktəb üçün interaktiv statistik dashboard. Mobil telefonda da işləyir (sidebar avtomatik menyuya yığılır).

Qovluq strukturu:
```
dashboard/
├─ app.py                  (əsas app — hər iki hostinq üçün əsas fayl)
├─ az_names.py             (adlar üzrə cins lüğəti)
├─ requirements.txt
├─ README.md
├─ .streamlit/config.toml  (dark tema)
└─ data/sagirdler.xlsx     (məlumat)
```

## Lokal işə salma

```bash
pip install -r requirements.txt
streamlit run app.py
```

Brauzerdə açılır: http://localhost:8501

## Pulsuz hosting

### Seçim A: Hugging Face Spaces (tövsiyə — GitHub lazım deyil)
1. https://huggingface.co → hesab yarat → yuxarıda **New** → **Space**.
2. `Owner`: istifadəçi adın, `Name`: məs. `sagird-statistikasi`, SDK: **Streamlit**. Create.
3. **Files** sekmesi → **Add file → Upload files** → bu qovluqdakı əsas faylları əlavə et:
   - `app.py`, `az_names.py`, `requirements.txt`, `.streamlit/config.toml`
   - `data/sagirdler.xlsx` (data qovluğunu da yükləyə bilərsən)
   - `README.md` (istəsən)
4. Deploy avtomatik başlayır. Hazır URL: `https://<user>-<space>.hf.space`

> Qeyd: Upload-dan sonra bir neçə dəqiqə "Building" olur, sonra açılır. Sleep/building zamanı yenidən yüklənməsi normaldır.

### Seçim B: Streamlit Community Cloud (GitHub ilə)
1. Bu qovluğu GitHub repoya yüklə (`app.py` reponun kökündə olmalıdır):
   ```bash
   git init
   git add .
   git commit -m "Sagird statistikasi dashboard"
   git branch -M main
   git remote add origin https://github.com/ISTIFADECI_ADIN/sagird-statistikasi.git
   git push -u origin main
   ```
2. https://share.streamlit.io (və ya streamlit.io/cloud) → **New app / Deploy** → reponu seç.
3. `Main file`: `app.py`, `App URL`: özün seçdiyin ad.
4. URL: `https://<ad>.streamlit.app`

## Qeydlər
- Cins təxmindir: 1) soyad şəkilçisi (`-ov/-yev` oğlan, `-ova/-yeva` qız), 2) ad lüğəti (`az_names.py`), 3) ad sonluğu.
- Yaş 2026 referans ilinə görə hesablanır.
- Məlumat mənbəyi: `data/sagirdler.xlsx`. Excel-ə yeni şagird əlavə etsən, bu faylı yeniləyib yenidən yüklə — dashboard avtomatik təzələnir.