import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(
    page_title="생산 Dashboard",
    layout="wide"
)

st.title("생산 Dashboard")

# -----------------------------
# 데이터 로드
# -----------------------------
DATA_PATH = Path("data/production_random_data_2026.txt")

@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", encoding="utf-8-sig")
    df["line"] = df["line"].astype(str)
    df["설비수"] = pd.to_numeric(df["설비수"], errors="coerce")
    df["wpd"] = pd.to_numeric(df["wpd"], errors="coerce")
    df["send"] = pd.to_numeric(df["send"], errors="coerce")
    df["capa"] = pd.to_numeric(df["capa"], errors="coerce")
    df["생산목표"] = pd.to_numeric(df["생산목표"], errors="coerce")
    return df

df = load_data(DATA_PATH)

# -----------------------------
# 월 정렬용 함수
# -----------------------------
def month_sort_key(month_text: str):
    # 예: "26년 1월" -> 1
    try:
        return int(month_text.split(" ")[1].replace("월", ""))
    except:
        return 999

month_options = sorted(df["생산월"].dropna().unique().tolist(), key=month_sort_key)
line_options = sorted(df["line"].dropna().unique().tolist(), key=lambda x: int(x))
dr_options = sorted(df["dr"].dropna().unique().tolist())

# -----------------------------
# 사이드바 필터
# -----------------------------
st.sidebar.header("필터")

selected_month = st.sidebar.selectbox("생산월", month_options, index=0)
selected_line = st.sidebar.selectbox("LINE", line_options, index=0)

filtered_dr_options = sorted(
    df[df["line"] == selected_line]["dr"].dropna().unique().tolist()
)
selected_dr = st.sidebar.selectbox("DR", filtered_dr_options, index=0)

# -----------------------------
# 공통 필터 데이터
# -----------------------------
df_line_dr = df[
    (df["line"] == selected_line) &
    (df["dr"] == selected_dr)
].copy()

df_selected = df[
    (df["생산월"] == selected_month) &
    (df["line"] == selected_line) &
    (df["dr"] == selected_dr)
].copy()

# -----------------------------
# KPI
# -----------------------------
col_kpi1, col_kpi2, col_kpi3 = st.columns(3)

if not df_selected.empty:
    target_value = df_selected["생산목표"].iloc[0]
    shortage_count = (df_selected["capa"] < target_value).sum()
    shortage_total = (target_value - df_selected["capa"]).clip(lower=0).sum()
    min_capa_value = df_selected["capa"].min()

    col_kpi1.metric("선택 조건 생산목표", f"{target_value:,.0f}")
    col_kpi2.metric("CAPA 부족 PRC 수", f"{shortage_count:,}")
    col_kpi3.metric("선택월 최소 CAPA", f"{min_capa_value:,.0f}")
else:
    col_kpi1.metric("선택 조건 생산목표", "-")
    col_kpi2.metric("CAPA 부족 PRC 수", "-")
    col_kpi3.metric("선택월 최소 CAPA", "-")

# -----------------------------
# 1번 그래프
# 생산월별 MIN CAPA + 생산목표
# line, dr 반응
# -----------------------------
st.subheader("1. 생산월별 MIN CAPA / 생산목표")

if df_line_dr.empty:
    st.warning("선택한 LINE/DR 조합에 데이터가 없습니다.")
else:
    monthly_summary = (
        df_line_dr.groupby("생산월", as_index=False)
        .agg(
            min_capa=("capa", "min"),
            생산목표=("생산목표", "first")
        )
    )

    monthly_summary["month_order"] = monthly_summary["생산월"].apply(month_sort_key)
    monthly_summary = monthly_summary.sort_values("month_order")

    fig1 = go.Figure()

    fig1.add_trace(
        go.Bar(
            x=monthly_summary["생산월"],
            y=monthly_summary["min_capa"],
            name="MIN CAPA",
            text=monthly_summary["min_capa"].apply(lambda x: f"{x:,.0f}"),
            textposition="outside"
        )
    )

    fig1.add_trace(
        go.Scatter(
            x=monthly_summary["생산월"],
            y=monthly_summary["생산목표"],
            mode="lines+markers+text",
            name="생산목표",
            text=monthly_summary["생산목표"].apply(lambda x: f"{x:,.0f}"),
            textposition="top center",
            line=dict(width=3)
        )
    )

    fig1.update_layout(
        title=f"생산월별 MIN CAPA / 생산목표 (LINE {selected_line}, DR {selected_dr})",
        xaxis_title="생산월",
        yaxis_title="수량",
        legend_title="구분",
        height=500
    )

    st.plotly_chart(fig1, use_container_width=True)

# -----------------------------
# 2번 그래프
# PRC별 CAPA + 생산목표
# CAPA 오름차순
# target보다 낮으면 빨간색 + 부족량 표기
# -----------------------------
st.subheader("2. PRC별 CAPA / 생산목표")

if df_selected.empty:
    st.warning("선택한 생산월/LINE/DR 조합에 데이터가 없습니다.")
else:
    df_capa = df_selected.copy().sort_values(by="capa", ascending=True)

    target_value = df_capa["생산목표"].iloc[0]

    colors = []
    shortage_labels = []
    custom_shortage = []

    for capa in df_capa["capa"]:
        if capa < target_value:
            shortage = target_value - capa
            colors.append("red")
            shortage_labels.append(f"-{shortage:,.0f}")
            custom_shortage.append(shortage)
        else:
            colors.append("#1f77b4")
            shortage_labels.append("")
            custom_shortage.append(0)

    fig2 = go.Figure()

    fig2.add_trace(
        go.Bar(
            x=df_capa["prc"],
            y=df_capa["capa"],
            name="CAPA",
            marker_color=colors,
            text=shortage_labels,
            textposition="outside",
            customdata=custom_shortage,
            hovertemplate=(
                "<b>PRC</b>: %{x}<br>"
                "<b>CAPA</b>: %{y:,.0f}<br>"
                "<b>부족량</b>: %{customdata:,.0f}<extra></extra>"
            )
        )
    )

    fig2.add_trace(
        go.Scatter(
            x=df_capa["prc"],
            y=[target_value] * len(df_capa),
            mode="lines+markers",
            name="생산목표",
            line=dict(color="black", width=3),
            hovertemplate=(
                "<b>PRC</b>: %{x}<br>"
                "<b>생산목표</b>: %{y:,.0f}<extra></extra>"
            )
        )
    )

    fig2.update_layout(
        title=f"PRC별 CAPA / 생산목표 ({selected_month}, LINE {selected_line}, DR {selected_dr})",
        xaxis_title="PRC",
        yaxis_title="수량",
        xaxis_tickangle=-45,
        legend_title="구분",
        height=600
    )

    st.plotly_chart(fig2, use_container_width=True)

    shortage_df = df_capa[df_capa["capa"] < target_value].copy()
    if not shortage_df.empty:
        shortage_df["부족량"] = target_value - shortage_df["capa"]
        st.markdown("**CAPA 부족 PRC 목록**")
        st.dataframe(
            shortage_df[["prc", "capa", "생산목표", "부족량", "send", "설비수"]]
            .sort_values("부족량", ascending=False),
            use_container_width=True
        )

# -----------------------------
# 3번 그래프
# PRC별 SEND
# -----------------------------
st.subheader("3. PRC별 SEND")

if df_selected.empty:
    st.warning("선택한 생산월/LINE/DR 조합에 데이터가 없습니다.")
else:
    df_send = df_selected.copy().sort_values(by="send", ascending=False)

    fig3 = go.Figure()

    fig3.add_trace(
        go.Bar(
            x=df_send["prc"],
            y=df_send["send"],
            name="SEND",
            text=df_send["send"].apply(lambda x: f"{x:,.0f}"),
            textposition="outside"
        )
    )

    fig3.update_layout(
        title=f"PRC별 SEND ({selected_month}, LINE {selected_line}, DR {selected_dr})",
        xaxis_title="PRC",
        yaxis_title="SEND",
        xaxis_tickangle=-45,
        height=500
    )

    st.plotly_chart(fig3, use_container_width=True)

# -----------------------------
# 4번 그래프
# PRC별 설비수
# -----------------------------
st.subheader("4. PRC별 설비수")

if df_selected.empty:
    st.warning("선택한 생산월/LINE/DR 조합에 데이터가 없습니다.")
else:
    df_eqp = df_selected.copy().sort_values(by="설비수", ascending=False)

    fig4 = go.Figure()

    fig4.add_trace(
        go.Bar(
            x=df_eqp["prc"],
            y=df_eqp["설비수"],
            name="설비수",
            text=df_eqp["설비수"].apply(lambda x: f"{x:,.0f}"),
            textposition="outside"
        )
    )

    fig4.update_layout(
        title=f"PRC별 설비수 ({selected_month}, LINE {selected_line}, DR {selected_dr})",
        xaxis_title="PRC",
        yaxis_title="설비수",
        xaxis_tickangle=-45,
        height=500
    )

    st.plotly_chart(fig4, use_container_width=True)

# -----------------------------
# 원본 데이터 보기
# -----------------------------
with st.expander("선택 조건 원본 데이터 보기"):
    if df_selected.empty:
        st.info("데이터가 없습니다.")
    else:
        st.dataframe(
            df_selected.sort_values(by="prc", ascending=True),
            use_container_width=True
        )