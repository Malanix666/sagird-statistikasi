import datetime
import io
import time

import altair as alt
import pandas as pd
import streamlit as st
from pathlib import Path

from az_names import MALE, FEMALE, norm
from jurnal_data import (
    CEDEVEL,
    DAY_TO_WEEKDAY,
    DOW_AZ,
    SCHOOL_END,
    SCHOOL_START,
    class_sort_key,
    lesson_columns,
    lesson_days,
)
from jurnal_parse import closest, fold, match_students, parse_command
from jurnal_store import (
    DEFAULT_BRANCH,
    DEFAULT_PATH,
    DEFAULT_REPO,
    deserialize as jurnal_from_github,
    fetch as jurnal_fetch,
    push as jurnal_push,
    serialize as jurnal_to_github,
    store_hash,
)

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


@st.cache_data
def class_names(df: pd.DataFrame) -> dict:
    """sinif -> ['Soyad Ad AtaAdi', ...] (ünvanlar da daxil)"""
    out = {}
    for sinif, g in df.groupby("Sinif"):
        saa = (
            g["Soyad"].fillna("").astype(str).str.strip()
            + " "
            + g["Ad"].fillna("").astype(str).str.strip()
            + " "
            + g["AtaAdi"].fillna("").astype(str).str.strip()
        ).str.strip()
        seen, dedup = {}, []
        for n in sorted(x for x in saa.tolist() if x):
            if n in seen:
                seen[n] += 1
                n = "%s (%d)" % (n, seen[n])
            else:
                seen[n] = 1
            dedup.append(n)
        out[sinif] = dedup
    return out


def _to_xlsx(frame: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    frame.to_excel(buf, index=True)
    return buf.getvalue()


def _sec(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


def gh_config():
    """GitHub saxlama konfiqurasiyası. Token yoxdursa None."""
    token = _sec("GITHUB_TOKEN")
    if not token:
        return None
    return {
        "token": str(token),
        "repo": str(_sec("GITHUB_REPO", DEFAULT_REPO)),
        "branch": str(_sec("GITHUB_BRANCH", DEFAULT_BRANCH)),
        "path": str(_sec("GITHUB_PATH", DEFAULT_PATH)),
    }


df = load_data()
CLASS_NAMES = class_names(df)


def _lesson_period(sinif, d):
    """Həmin tarixdə sinfin dərs periodu (yoxdursa None)."""
    cols = lesson_columns(sinif, d, d)
    return cols[0][1] if cols else None


def _quick_apply(sinif, d, period, value, targets) -> str:
    store = st.session_state.setdefault("jurnal_store", {})
    changes = []
    for n in targets:
        key = (sinif, n, d.isoformat(), period)
        changes.append((key, store.get(key)))
        store[key] = value
    st.session_state["jurnal_undo"] = {
        "changes": changes,
        "label": "%s · %s · %d nəfər → %s" % (sinif, d.strftime("%d.%m"), len(targets), value),
    }
    kim = ", ".join(t.split()[0] for t in targets[:5])
    if len(targets) > 5:
        kim += ", …"
    return "%s · %d. dərs · **%s** → %s (%d nəfər)" % (
        d.strftime("%d.%m.%Y"), period, value, kim, len(targets),
    )


def _quick_run(text, chosen=None, amb=None, switch=False) -> dict:
    sinif_cur = st.session_state.get("jurnal_sinif")
    parsed = parse_command(text, sinif_cur)
    if parsed["errors"]:
        return {"ok": False, "msg": " · ".join(parsed["errors"])}
    sinif = parsed["sinif"] or sinif_cur
    d, value = parsed["date"], parsed["value"]
    if value is None:
        return {"ok": False, "msg": "Dəyər tapılmadı — `qaib`, `yox idi`, `5`, `qiymət 4` yazın."}
    if d is None:
        return {"ok": False, "msg": "Tarix verilmədi — `bu gün`, `dünən` və ya `12.10.2026` yazın."}
    period = _lesson_period(sinif, d)
    if period is None:
        return {
            "ok": False,
            "msg": "%s tarixində %s sinfində dərs yoxdur (tətil/bayram və ya həmin gün dərs deyil)."
            % (d.strftime("%d.%m.%Y"), sinif),
        }
    names = CLASS_NAMES.get(sinif, [])
    if not names:
        return {"ok": False, "msg": "%s sinfində şagird siyahısı tapılmadı." % sinif}

    if parsed["whole_class"]:
        targets = list(names)
    else:
        queries = parsed["queries"]
        if not queries:
            return {"ok": False, "msg": "Şagird adı yazın (və ya `hamısı`)."}
        targets = []
        for q in queries:
            if chosen and amb and q == amb:
                targets.append(chosen)
                continue
            hits = match_students(q, names)
            if not hits:
                return {
                    "ok": False,
                    "msg": "`%s` — %s sinfində tapılmadı." % (q, sinif),
                    "suggest": closest(q, names),
                }
            if len(hits) > 1:
                return {
                    "ok": False,
                    "msg": "`%s` — %d nəfər uyğun gəlir, hansı?" % (q, len(hits)),
                    "pending": {"text": text, "amb": q, "candidates": hits[:8]},
                }
            targets.append(hits[0])

    if switch:
        st.session_state["jurnal_sinif"] = sinif
        js, je = st.session_state.get("jurnal_start"), st.session_state.get("jurnal_end")
        if js and d < js:
            st.session_state["jurnal_start"] = d
        if je and d > je:
            st.session_state["jurnal_end"] = d

    return {"ok": True, "msg": _quick_apply(sinif, d, period, value, targets)}


def _quick_submit():
    text = (st.session_state.get("jurnal_quick") or "").strip()
    st.session_state["jurnal_quick"] = ""
    st.session_state["jurnal_result"] = None
    st.session_state["jurnal_pending"] = None
    if not text:
        return
    res = _quick_run(text, switch=True)
    st.session_state["jurnal_result"] = res
    st.session_state["jurnal_pending"] = res.get("pending")


def _quick_pick(cand):
    pend = st.session_state.get("jurnal_pending") or {}
    st.session_state["jurnal_result"] = _quick_run(
        pend.get("text", ""), chosen=cand, amb=pend.get("amb")
    )
    st.session_state["jurnal_pending"] = None


def _quick_undo():
    u = st.session_state.pop("jurnal_undo", None)
    store = st.session_state.setdefault("jurnal_store", {})
    if u:
        for key, old in u["changes"]:
            if old is None:
                store.pop(key, None)
            else:
                store[key] = old
    st.session_state["jurnal_result"] = None
    st.session_state["jurnal_pending"] = None

with st.sidebar:
    st.subheader("Filterlər")
    sinifler = (
        df.dropna(subset=["Sinif"]).sort_values(["SinifNo", "Sinif"])["Sinif"].unique().tolist()
    )
    st.markdown("**Sinf** (bütün siniflər seçilib)")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Hamısını seç", use_container_width=True):
            for s in sinifler:
                st.session_state[f"sinif_{s}"] = True
            st.rerun()
    with b2:
        if st.button("Hamısını sil", use_container_width=True):
            for s in sinifler:
                st.session_state[f"sinif_{s}"] = False
            st.rerun()
    s_cols = st.columns(3)
    for i, s in enumerate(sinifler):
        with s_cols[i % 3]:
            st.checkbox(s, value=True, key=f"sinif_{s}")
    sec_sinif = {s for s in sinifler if st.session_state.get(f"sinif_{s}", True)}

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

tab_umumi, tab_aile, tab_siyah, tab_jurnal = st.tabs(
    [
        ":material/bar_chart: Ümumi statistika",
        ":material/family_history: Ailələr",
        ":material/table_rows: Şagird siyahısı",
        ":material/book: Formativ jurnal",
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

with tab_jurnal:
    st.subheader("Formativ qiymətləndirmə jurnalı")

    gh_cfg = gh_config()
    if gh_cfg and "jurnal_remote_done" not in st.session_state:
        remote = jurnal_fetch(gh_cfg)
        st.session_state["jurnal_remote_done"] = True
        st.session_state["jurnal_remote_ok"] = remote is not None
        if remote:
            st.session_state["jurnal_store"] = jurnal_from_github(remote)

    j1, j2, j3 = st.columns([3, 2, 2])
    with j1:
        sinif_j = st.selectbox(
            "Sinif",
            sorted(CEDEVEL.keys(), key=class_sort_key),
            key="jurnal_sinif",
        )
    with j2:
        j_start = st.date_input("Başlanğıc", value=SCHOOL_START, key="jurnal_start")
    with j3:
        j_end = st.date_input("Son", value=SCHOOL_END, key="jurnal_end")

    with st.container(border=True):
        st.markdown("**Sürətli qeyd** — sətir yazın və Enter basın")
        st.text_input(
            "Sürətli qeyd",
            key="jurnal_quick",
            on_change=_quick_submit,
            label_visibility="collapsed",
            placeholder="bu gün 5a filankesov filankes qaib   ·   dünən 7b məmmədova aysel 5   ·   12.10.2026 5a hamısı qaib",
        )
        res = st.session_state.get("jurnal_result")
        if res:
            if res.get("ok"):
                st.success(res["msg"])
                u = st.session_state.get("jurnal_undo")
                if u:
                    st.button(
                        "Ləğv et — %s" % u["label"],
                        key="jurnal_undo_btn",
                        on_click=_quick_undo,
                    )
            else:
                st.error(res.get("msg", ""))
                if res.get("suggest"):
                    st.caption("Ən oxşarlar: " + ", ".join(res["suggest"]))
                pend = st.session_state.get("jurnal_pending")
                if pend and pend.get("candidates"):
                    st.caption("Hansı şagirddir?")
                    row = st.columns(min(len(pend["candidates"]), 4))
                    for i, cand in enumerate(pend["candidates"]):
                        with row[i % len(row)]:
                            st.button(
                                cand,
                                key="jpend_%d" % i,
                                use_container_width=True,
                                on_click=_quick_pick,
                                args=(cand,),
                            )
        else:
            st.caption(
                "Dəstəklənən: `bu gün` / `dünən` / `12.10.2026` · `5a` · şagird adı · "
                "`qaib` / `yox idi` / `1`–`5` / `qiymət 4` · `hamısı` · `əliyev, məmmədov qaib`"
            )

    slots = lesson_days(sinif_j)
    dows = sorted({DAY_TO_WEEKDAY[d] for d, _ in slots})
    st.caption(
        "Həftədə %d dərs: %s · tətil/bayram günləri avtomatik atlanır · "
        "xanalara `qaib` və ya qiymət (1–5) yazın"
        % (len(slots), ", ".join(DOW_AZ[w] for w in dows))
    )

    cols = lesson_columns(sinif_j, j_start, j_end)

    saalar = CLASS_NAMES.get(sinif_j, [])

    if not cols:
        st.info("Seçilmiş tarix aralığında bu sinifdə dərs yoxdur.")
    elif not saalar:
        st.info("Bu sinifdə şagird siyahısı yoxdur.")
    else:
        indeks = list(saalar)

        tarixler = [d for d, _ in cols]
        tekrar = {d for d in tarixler if tarixler.count(d) > 1}
        labels = []
        for d, p in cols:
            lb = "%d.%02d %s" % (d.day, d.month, DOW_AZ[d.weekday()])
            if d in tekrar:
                lb += " · %d" % p
            labels.append(lb)

        skel = pd.DataFrame(
            "",
            index=pd.Index(indeks, name="Şagirdin soyadı, adı, atasının adı"),
            columns=labels,
        )
        store = st.session_state.setdefault("jurnal_store", {})
        st.session_state.setdefault("jurnal_saved_hash", store_hash(store))
        for (d, p), lb in zip(cols, labels):
            for n in indeks:
                skel.at[n, lb] = store.get((sinif_j, n, d.isoformat(), p), "")

        wkey = "jed_%s_%s_%s" % (sinif_j, j_start.isoformat(), j_end.isoformat())
        edited = st.data_editor(
            skel,
            key=wkey,
            width="stretch",
            hide_index=False,
            column_config={
                lb: st.column_config.TextColumn(lb, width="small") for lb in labels
            },
        )

        for (d, p), lb in zip(cols, labels):
            for n in indeks:
                v = edited.at[n, lb]
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    v = ""
                key = (sinif_j, n, d.isoformat(), p)
                if str(v).strip():
                    store[key] = str(v).strip()
                else:
                    # boş xana: dəyəri sil ki, GitHub-a da ötürülsün
                    store.pop(key, None)

        f1, f2 = st.columns([1, 4])
        with f1:
            st.download_button(
                "Excel jurnalı yüklə",
                data=_to_xlsx(edited),
                file_name="formativ_jurnal_%s.xlsx" % sinif_j,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    store_all = st.session_state.setdefault("jurnal_store", {})
    saved_hash = st.session_state.setdefault("jurnal_saved_hash", store_hash(store_all))
    dirty = store_hash(store_all) != saved_hash

    st.divider()
    s1, s2, s3 = st.columns([3, 2, 3])
    with s1:
        if gh_cfg:
            if st.button(
                "GitHub-a saxla",
                type="primary" if dirty else "secondary",
                use_container_width=True,
            ):
                ok, msg = jurnal_push(gh_cfg, jurnal_to_github(store_all))
                if ok:
                    st.session_state["jurnal_saved_hash"] = store_hash(store_all)
                    st.session_state["jurnal_last_save"] = time.strftime("%d.%m.%Y %H:%M:%S")
                    st.success(msg)
                else:
                    st.error(msg)
        else:
            st.button(
                "GitHub-a saxla (token yoxdur)",
                disabled=True,
                use_container_width=True,
            )
    with s2:
        if st.session_state.get("jurnal_last_save"):
            st.caption("Son saxlanış: %s" % st.session_state["jurnal_last_save"])
        elif not gh_cfg:
            st.caption("Token quraşdırılmayıb")
        else:
            st.caption("Saxlanılmayıb")
    with s3:
        if not gh_cfg:
            st.warning(
                "GitHub token yoxdur — qeydlər yalnız bu brauzer sessiyasında qalır. "
                "`GITHUB_TOKEN` əlavə edin (secrets.example.toml baxın)."
            )
        elif not st.session_state.get("jurnal_remote_ok", True):
            st.error("GitHub-dan əvvəlki qeydləri oxumaq mümkün olmadı — yoxlayın: token, repo adı, icazə.")
        elif dirty:
            st.warning("Saxlanılmamış dəyişikliklər var — **GitHub-a saxla** düyməsinə basın.")
        else:
            st.success("Bütün qeydlər GitHub-da saxlanılıb.")

st.caption("Məlumat mənbəyi: H.Z.Tağıyev adına 123 №-li tam orta məktəb · 2026/2027 tədris ili")