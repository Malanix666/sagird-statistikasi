import datetime

import altair as alt
import pandas as pd
import streamlit as st
from pathlib import Path

from az_names import MALE, FEMALE, norm

st.set_page_config(
    page_title="123 №-li məktəb — Şagird statistikası",
    page_icon=":material/school:",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA = Path(__file__).parent / "data" / "sagirdler.xlsx"
REF_YEAR = 2026

COLUMNS = {
    "Soyad": "Soyad",
    "Ad": "Ad",
    "Ata Adı": "AtaAdi",
    "Təvəllüd": "Tevellud",
    "Sinif": "Sinif",
    "Qohumluq": "Qohumluq",
    "Soyad.1": "Kok",
    "Tam soyad ad": "Aile",
    "Filtrele": "QohumluqVar",
}


@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_excel(DATA)
    df = df.rename(columns=COLUMNS)
    df = df[list(COLUMNS.values())].copy()

    df["Tevellud"] = pd.to_datetime(df["Tevellud"], errors="coerce")
    df["No"] = df.index + 1

    def cins_tahmin(soyad, ad):
        s = norm(soyad)
        if s.endswith(("OVA", "YEVA")):
            return "Qız"
        if s.endswith(("OV", "YEV")):
            return "Oğlan"
        a = norm(ad)
        if a in MALE:
            return "Oğlan"
        if a in FEMALE:
            return "Qız"
        if a.endswith(("A", "Ə")):
            return "Qız"
        return "Naməlum"

    df["Cins"] = [cins_tahmin(s, a) for s, a in zip(df["Soyad"], df["Ad"])]

    df["DogumIli"] = df["Tevellud"].dt.year
    df["Yas"] = (REF_YEAR - df["DogumIli"]).where(df["DogumIli"].notna())

    df["Sinif"] = df["Sinif"].astype(str).str.strip().str.lower()
    df["SinifNo"] = (
        df["Sinif"].str.extract(r"(\d+)")[0].astype("Int64")
    )
    df["Qohumluq"] = df["Qohumluq"].fillna("").astype(str).str.strip()
    df["QohumluqVar"] = df["Qohumluq"].ne("")
    df["Aile"] = df["Aile"].fillna("").astype(str).str.strip()

    aile_size = df.groupby("Aile")["Aile"].transform("size")
    df["AileOlcusu"] = aile_size

    return df


@st.cache_data
def family_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for aile, g in df.groupby("Aile"):
        if not aile:
            continue
        kids = ", ".join(f"{r.Ad} {r.Sinif}" for r in g.itertuples())
        rows.append(
            {
                "Ailə": aile,
                "Övlad sayı": len(g),
                "Övladlar": kids,
            }
        )
    fam = pd.DataFrame(rows)
    return fam.sort_values("Övlad sayı", ascending=False).reset_index(drop=True)


@st.cache_data
def twin_count(df: pd.DataFrame) -> int:
    twins = df[df["Aile"] != ""].groupby(["Aile", "Tevellud"]).size()
    ones = twins[twins >= 2]
    return int(ones.sum())


df = load_data()

with st.sidebar:
    st.subheader("Filterlər")
    sinifler = (
        df.dropna(subset=["Sinif"]).sort_values(["SinifNo", "Sinif"])["Sinif"].unique().tolist()
    )
    no_col = df.dropna(subset=["Sinif"]).groupby("Sinif")["SinifNo"].first()
    qrup_1_4 = "1-4 siniflər"
    qrup_5_11 = "5-11 siniflər"
    sec_raw = st.multiselect(
        "Sinf",
        [qrup_1_4, qrup_5_11] + sinifler,
        default=[qrup_1_4, qrup_5_11],
        help="Bütün siniflər: '1-4 siniflər' və '5-11 siniflər' seçili burax. Tək sinif seçmək üçün qrupların işarəsini söndürüb birini seç.",
    )
    sec_sinif = set(sec_raw)
    sec_sinif.discard(qrup_1_4)
    sec_sinif.discard(qrup_5_11)
    if qrup_1_4 in sec_raw:
        sec_sinif |= {s for s in sinifler if no_col[s] <= 4}
    if qrup_5_11 in sec_raw:
        sec_sinif |= {s for s in sinifler if no_col[s] >= 5}

    cinsler = ["Hamısı", "Oğlan", "Qız", "Naməlum"]
    sec_cins = st.segmented_control("Cins", cinsler, default="Hamısı")

    qohumluq = st.selectbox(
        "Qohumluq", ["Hamısı", "Qohumluğu olanlar", "Qohumluğu olmayanlar"]
    )

    yas_min, yas_max = (
        int(df["Yas"].min()),
        int(df["Yas"].max()),
    )
    sec_yas = st.slider("Yaş (2026)", yas_min, yas_max, (yas_min, yas_max))

subset = df[df["Sinif"].isin(sec_sinif)].copy()
if sec_cins != "Hamısı":
    subset = subset[subset["Cins"] == sec_cins]
if sec_yas[0] != yas_min or sec_yas[1] != yas_max:
    subset = subset[subset["Yas"].between(*sec_yas)]
if qohumluq == "Qohumluğu olanlar":
    subset = subset[subset["QohumluqVar"]]
elif qohumluq == "Qohumluğu olmayanlar":
    subset = subset[~subset["QohumluqVar"]]

st.title("123 №-li tam orta məktəb")
st.caption("Şagird statistikası · 2026/2027 tədris ili")

aile_say = int(subset[subset["Aile"] != ""]["Aile"].nunique())
qohumlu_say = int(subset["QohumluqVar"].sum())
qiz = int((subset["Cins"] == "Qız").sum())
oglan = int((subset["Cins"] == "Oğlan").sum())
namelum = int((subset["Cins"] == "Naməlum").sum())

with st.container(horizontal=True):
    st.metric("Cəmi şagird", f"{len(subset):,}", border=True)
    st.metric("Sinf", subset["Sinif"].nunique(), border=True)
    st.metric("Ailə (qohumluq qrupu)", aile_say, border=True)
    st.metric("Qohumluğu olan şagird", qohumlu_say, border=True)
    st.metric("Oğlan · Qız", f"{oglan} · {qiz}", border=True)
    if namelum:
        st.metric("Naməlum cins", namelum, border=True)

tab_umumi, tab_aile, tab_siyah = st.tabs(
    [
        ":material/bar_chart: Ümumi statistika",
        ":material/family_history: Ailələr",
        ":material/table_rows: Şagird siyahısı",
    ]
)

with tab_umumi:
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.subheader("Sinf üzrə şagird sayı")
            sinif_say = (
                subset.groupby("Sinif").size().reset_index(name="Şagird sayı")
            )
            sinif_say = sinif_say.sort_values("Sinif", key=lambda s: s.str.extract(r"(\d+)")[0].astype(int))
            chart = (
                alt.Chart(sinif_say)
                .mark_bar(color="#4C78A8")
                .encode(
                    x=alt.X("Sinif:N", title="Sinf", sort=None),
                    y=alt.Y("Şagird sayı:Q", title="Şagird"),
                    tooltip=["Sinif", "Şagird sayı"],
                )
            )
            st.altair_chart(chart, width="stretch")

        with st.container(border=True):
            st.subheader("Cins üzrə şagird sayı")
            cins_say = subset["Cins"].value_counts().reset_index()
            cins_say.columns = ["Cins", "Şagird sayı"]
            colors = ["#4C78A8", "#F58518", "#9AA0A4"]
            pie = (
                alt.Chart(cins_say)
                .mark_arc(innerRadius=50)
                .encode(
                    color=alt.Color("Cins:N", scale=alt.Scale(domain=list(cins_say["Cins"]), range=colors[: len(cins_say)])),
                    theta=alt.Theta("Şagird sayı:Q"),
                    tooltip=["Cins", "Şagird sayı"],
                )
            )
            st.altair_chart(pie, width="stretch")
            st.caption("Cins təxmindir: 1) soyad şəkilçisi (-ov/-yev oğlan, -ova/-yeva qız), 2) ad lüğəti (İlqar, Rza → oğlan; Aysel, Nuray → qız), 3) ad sonluğu (-a/-ə → qız).")

    with col2:
        with st.container(border=True):
            st.subheader("Sinf üzrə cins tərkibi")
            cins_sinif = (
                subset.groupby(["SinifNo", "Sinif", "Cins"])
                .size()
                .reset_index(name="Şagird sayı")
                .sort_values(["SinifNo", "Sinif"])
            )
            stack = (
                alt.Chart(cins_sinif)
                .mark_bar()
                .encode(
                    x=alt.X("Sinif:N", title="Sinf", sort=None),
                    y=alt.Y("Şagird sayı:Q", title="Şagird"),
                    color=alt.Color(
                        "Cins:N",
                        scale=alt.Scale(domain=["Qız", "Oğlan", "Naməlum"], range=["#F58518", "#4C78A8", "#9AA0A4"]),
                    ),
                    tooltip=["Sinif", "Cins", "Şagird sayı"],
                )
            )
            st.altair_chart(stack, width="stretch")

        with st.container(border=True):
            st.subheader("Yaş paylanması")
            yassub = subset[subset["Yas"].notna()].copy()
            yassub["YasCat"] = yassub["Yas"].astype(int)
            yas_counts = yassub.groupby("YasCat").size().reset_index(name="Şagird sayı")
            yas_hist = (
                alt.Chart(yas_counts)
                .mark_bar(color="#54A24B")
                .encode(
                    x=alt.X("YasCat:O", title="Yaş (2026)"),
                    y=alt.Y("Şagird sayı:Q", title="Şagird"),
                    tooltip=["YasCat", "Şagird sayı"],
                )
            )
            st.altair_chart(yas_hist, width="stretch")

with tab_aile:
    with st.container(horizontal=True):
        aileler = subset[subset["Aile"] != ""]
        aile_olcu = aileler.groupby("Aile").size()
        st.metric("Ailə qrupu", aile_say, border=True)
        st.metric("2+ övladı olan ailə", int((aile_olcu >= 2).sum()), border=True)
        st.metric("Eyni doğum gününü paylaşan bacı-qardaş", twin_count(subset), border=True)

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.subheader("Ailə ölçüsü paylanması")
            sizes = (
                subset[subset["Aile"] != ""]
                .groupby("Aile")
                .size()
                .rename("Ölçü")
                .value_counts()
                .reset_index()
            )
            sizes.columns = ["Övlad sayı", "Ailə sayı"]
            bar = (
                alt.Chart(sizes)
                .mark_bar(color="#F58518")
                .encode(
                    x=alt.X("Övlad sayı:N", title="Bir ailədən olan övlad"),
                    y=alt.Y("Ailə sayı:Q", title="Ailə"),
                    tooltip=["Övlad sayı", "Ailə sayı"],
                )
            )
            st.altair_chart(bar, width="stretch")

    with col2:
        with st.container(border=True):
            st.subheader("Ən böyük ailələr")
            fam = family_stats(df)
            fam = fam[fam["Övlad sayı"] >= 3]
            st.dataframe(
                fam.head(15),
                column_config={
                    "Ailə": st.column_config.TextColumn("Ailə"),
                    "Övlad sayı": st.column_config.NumberColumn("Övlad sayı"),
                    "Övladlar": st.column_config.TextColumn("Övladlar"),
                },
                hide_index=True,
                width="stretch",
            )

    with st.container(border=True):
        st.subheader("Ailələr (qohumluq qrupu)")
        fam_all = family_stats(subset)
        st.dataframe(
            fam_all,
            column_config={
                "Ailə": st.column_config.TextColumn("Ailə"),
                "Övlad sayı": st.column_config.NumberColumn("Övlad sayı"),
                "Övladlar": st.column_config.TextColumn("Övladlar"),
            },
            hide_index=True,
            width="stretch",
        )

with tab_siyah:
    with st.container(border=True):
        st.subheader("Şagird siyahısı")
        view = subset[
            ["No", "Soyad", "Ad", "AtaAdi", "Tevellud", "Sinif", "Cins", "Yas", "Qohumluq"]
        ].copy()
        view["Tevellud"] = [
            d.date() if pd.notna(d) else None for d in view["Tevellud"]
        ]
        axtar = st.text_input(
            "Axtar (ad, soyad, ata adı və ya sinif)",
            placeholder="Məs: Rzayeva, Leyla və ya 5a",
        )
        if axtar.strip():
            q = axtar.strip().casefold()
            view["_axtar"] = (
                view["Soyad"].fillna("")
                + " "
                + view["Ad"].fillna("")
                + " "
                + view["AtaAdi"].fillna("")
                + " "
                + view["Sinif"].fillna("")
            ).str.casefold()
            view = view[view["_axtar"].str.contains(q, na=False)].drop(columns=["_axtar"])
        st.caption(f"{len(view)} şagird göstərilir")
        st.dataframe(
            view,
            column_config={
                "Tevellud": st.column_config.DateColumn("Təvəllüd", format="DD.MM.YYYY"),
                "Cins": st.column_config.TextColumn("Cins"),
                "Yas": st.column_config.NumberColumn("Yaş", format="%d"),
                "Qohumluq": st.column_config.TextColumn("Qohumluq"),
            },
            hide_index=True,
            width="stretch",
        )

st.caption("Məlumat mənbəyi: H.Z.Tağıyev adına 123 №-li tam orta məktəb · 2026/2027 tədris ili")