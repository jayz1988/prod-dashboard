import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path

st.set_page_config(
    page_title="반도체 생산 CAPA Dashboard",
    layout="wide"
)

st.title("반도체 생산 CAPA Dashboard")
st.caption("생산월 / LINE / DR 기준 CAPA, SEND, 설비수, 병목 PRC를 분석하는 대시보드")

# =========================================================
# 데이터 로드
# =========================================================
DATA_PATH = Path("data/production_random_data_2026.txt")


@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", encoding="utf-8-sig")

    df["생산월"] = df["생산월"].astype(str)
    df["line"] = df["line"].astype(str)
    df["prc"] = df["prc"].astype(str)
    df["model"] = df["model"].astype(str)
    df["dr"] = df["dr"].astype(str)

    numeric_cols = ["설비수", "wpd", "send", "capa", "생산목표"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


df = load_data(DATA_PATH)


# =========================================================
# 공통 함수
# =========================================================
def month_sort_key(month_text: str) -> int:
    try:
        return int(month_text.split(" ")[1].replace("월", ""))
    except Exception:
        return 999


def fmt_num(x):
    if pd.isna(x):
        return "-"
    return f"{x:,.0f}"


def join_prc_names(prc_list, max_show=10):
    prc_list = [str(x) for x in prc_list if pd.notna(x)]
    if not prc_list:
        return "없음"
    if len(prc_list) <= max_show:
        return ", ".join(prc_list)
    return ", ".join(prc_list[:max_show]) + f" 외 {len(prc_list) - max_show}개"


# =========================================================
# 사이드바 필터
# =========================================================
st.sidebar.header("필터")

month_options = sorted(df["생산월"].dropna().unique().tolist(), key=month_sort_key)
line_options = sorted(df["line"].dropna().unique().tolist(), key=lambda x: int(x))

selected_month = st.sidebar.selectbox("생산월", month_options, index=0)
selected_line = st.sidebar.selectbox("LINE", line_options, index=0)

filtered_dr_options = sorted(
    df[df["line"] == selected_line]["dr"].dropna().unique().tolist()
)
selected_dr = st.sidebar.selectbox("DR", filtered_dr_options, index=0)

# =========================================================
# 필터 데이터
# =========================================================
df_line_dr = df[
    (df["line"] == selected_line) &
    (df["dr"] == selected_dr)
].copy()

df_selected = df[
    (df["생산월"] == selected_month) &
    (df["line"] == selected_line) &
    (df["dr"] == selected_dr)
].copy()

if df_selected.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다.")
    st.stop()

target_value = df_selected["생산목표"].iloc[0]

df_selected["부족량"] = (target_value - df_selected["capa"]).clip(lower=0)
df_selected["달성여부"] = df_selected["capa"].apply(lambda x: "미달" if x < target_value else "달성")
df_selected["가동여유"] = df_selected["capa"] - target_value
df_selected["capa_send_sum"] = df_selected["capa"] + df_selected["send"]
df_selected["capa_send_부족량"] = (target_value - df_selected["capa_send_sum"]).clip(lower=0)
df_selected["send_capa_ratio"] = df_selected.apply(
    lambda r: (r["send"] / r["capa"] * 100) if pd.notna(r["capa"]) and r["capa"] != 0 else 0,
    axis=1
)

# =========================================================
# KPI
# =========================================================
st.subheader("요약 KPI")

total_prc = len(df_selected)
shortage_count = int((df_selected["capa"] < target_value).sum())
shortage_total = df_selected["부족량"].sum()
avg_capa = df_selected["capa"].mean()
min_capa = df_selected["capa"].min()
avg_send = df_selected["send"].mean()

kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

kpi1.metric("생산목표", fmt_num(target_value))
kpi2.metric("PRC 수", fmt_num(total_prc))
kpi3.metric("CAPA 부족 PRC", fmt_num(shortage_count))
kpi4.metric("총 부족량", fmt_num(shortage_total))
kpi5.metric("평균 CAPA", fmt_num(avg_capa))
kpi6.metric("평균 SEND", fmt_num(avg_send))

st.divider()

# =========================================================
# 1. 생산월별 MIN CAPA / 생산목표
#    - hover에 부족 PRC 개수/이름 표시
# =========================================================
st.subheader("1. 생산월별 MIN CAPA / 생산목표")

monthly_detail = df_line_dr.copy()
monthly_detail["부족여부"] = monthly_detail["capa"] < monthly_detail["생산목표"]

monthly_shortage = (
    monthly_detail.groupby("생산월")
    .apply(
        lambda g: pd.Series({
            "부족_prc_수": int((g["capa"] < g["생산목표"]).sum()),
            "부족_prc_이름": join_prc_names(
                g.loc[g["capa"] < g["생산목표"], "prc"].tolist(),
                max_show=12
            )
        })
    )
    .reset_index()
)

monthly_summary = (
    df_line_dr.groupby("생산월", as_index=False)
    .agg(
        min_capa=("capa", "min"),
        생산목표=("생산목표", "first")
    )
    .merge(monthly_shortage, on="생산월", how="left")
)

monthly_summary["month_order"] = monthly_summary["생산월"].apply(month_sort_key)
monthly_summary = monthly_summary.sort_values("month_order")

fig1 = go.Figure()

fig1.add_trace(
    go.Bar(
        x=monthly_summary["생산월"],
        y=monthly_summary["min_capa"],
        name="MIN CAPA",
        text=monthly_summary["min_capa"].apply(fmt_num),
        textposition="outside",
        customdata=monthly_summary[["생산목표", "부족_prc_수", "부족_prc_이름"]],
        hovertemplate=(
            "<b>생산월</b>: %{x}<br>"
            "<b>MIN CAPA</b>: %{y:,.0f}<br>"
            "<b>생산목표</b>: %{customdata[0]:,.0f}<br>"
            "<b>부족 PRC 수</b>: %{customdata[1]:,.0f}<br>"
            "<b>부족 PRC</b>: %{customdata[2]}<extra></extra>"
        )
    )
)

fig1.add_trace(
    go.Scatter(
        x=monthly_summary["생산월"],
        y=monthly_summary["생산목표"],
        mode="lines+markers+text",
        name="생산목표",
        text=monthly_summary["생산목표"].apply(fmt_num),
        textposition="top center",
        line=dict(color="black", width=3),
        hovertemplate=(
            "<b>생산월</b>: %{x}<br>"
            "<b>생산목표</b>: %{y:,.0f}<extra></extra>"
        )
    )
)

fig1.update_layout(
    title=f"생산월별 MIN CAPA / 생산목표 (LINE {selected_line}, DR {selected_dr})",
    xaxis_title="생산월",
    yaxis_title="수량",
    height=500
)

st.plotly_chart(fig1, use_container_width=True)

# =========================================================
# 2. PRC별 CAPA / 생산목표
#    - CAPA 오름차순
#    - 목표 미달 빨간색
#    - 부족량 라벨 표시
#    - SEND 누적 bar 추가
# =========================================================
st.subheader("2. PRC별 CAPA / 생산목표 / SEND")

df_capa = df_selected.sort_values(by="capa", ascending=True).copy()

capa_colors = df_capa["capa"].apply(lambda x: "red" if x < target_value else "#1f77b4")
send_colors = df_capa["capa"].apply(lambda x: "#ffb3b3" if x < target_value else "#9ecae1")
shortage_labels = df_capa["부족량"].apply(lambda x: f"-{x:,.0f}" if x > 0 else "")

fig2 = go.Figure()

fig2.add_trace(
    go.Bar(
        x=df_capa["prc"],
        y=df_capa["capa"],
        name="CAPA",
        marker_color=capa_colors,
        text=shortage_labels,
        textposition="outside",
        customdata=df_capa[["생산목표", "부족량", "설비수", "send", "capa_send_sum"]],
        hovertemplate=(
            "<b>PRC</b>: %{x}<br>"
            "<b>CAPA</b>: %{y:,.0f}<br>"
            "<b>SEND</b>: %{customdata[3]:,.0f}<br>"
            "<b>CAPA+SEND</b>: %{customdata[4]:,.0f}<br>"
            "<b>생산목표</b>: %{customdata[0]:,.0f}<br>"
            "<b>부족량</b>: %{customdata[1]:,.0f}<br>"
            "<b>설비수</b>: %{customdata[2]:,.0f}<extra></extra>"
        )
    )
)

fig2.add_trace(
    go.Bar(
        x=df_capa["prc"],
        y=df_capa["send"],
        name="SEND",
        marker_color=send_colors,
        customdata=df_capa[["capa", "생산목표", "capa_send_sum"]],
        hovertemplate=(
            "<b>PRC</b>: %{x}<br>"
            "<b>SEND</b>: %{y:,.0f}<br>"
            "<b>CAPA</b>: %{customdata[0]:,.0f}<br>"
            "<b>생산목표</b>: %{customdata[1]:,.0f}<br>"
            "<b>CAPA+SEND</b>: %{customdata[2]:,.0f}<extra></extra>"
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
    title=f"PRC별 CAPA / 생산목표 / SEND ({selected_month}, LINE {selected_line}, DR {selected_dr})",
    xaxis_title="PRC",
    yaxis_title="수량",
    xaxis_tickangle=-45,
    height=650,
    barmode="stack"
)

st.plotly_chart(fig2, use_container_width=True)

shortage_df = df_capa[df_capa["capa"] < target_value].copy()
if not shortage_df.empty:
    st.markdown("**CAPA 부족 PRC 목록**")
    st.dataframe(
        shortage_df[["prc", "model", "capa", "send", "capa_send_sum", "생산목표", "부족량", "설비수", "wpd"]]
        .sort_values(["부족량", "capa"], ascending=[False, True])
        .reset_index(drop=True),
        use_container_width=True
    )

# =========================================================
# 3. PRC별 SEND
# =========================================================
st.subheader("3. PRC별 SEND")

df_send = df_selected.sort_values(by="send", ascending=False).copy()

fig3 = go.Figure()

fig3.add_trace(
    go.Bar(
        x=df_send["prc"],
        y=df_send["send"],
        name="SEND",
        text=df_send["send"].apply(fmt_num),
        textposition="outside",
        marker_color="#2ca02c"
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

# =========================================================
# 4. PRC별 설비수
# =========================================================
st.subheader("4. PRC별 설비수")

df_eqp = df_selected.sort_values(by="설비수", ascending=False).copy()

fig4 = go.Figure()

fig4.add_trace(
    go.Bar(
        x=df_eqp["prc"],
        y=df_eqp["설비수"],
        name="설비수",
        text=df_eqp["설비수"].apply(fmt_num),
        textposition="outside",
        marker_color="#9467bd"
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

st.divider()

# =========================================================
# 5. 병목 PRC 분석
# =========================================================
st.subheader("5. 병목 PRC 분석")

left_col, right_col = st.columns([1.2, 1])

bottleneck_df = df_selected.copy()
bottleneck_df["병목점수"] = (
    bottleneck_df["부족량"] * 0.6 +
    bottleneck_df["설비수"].rank(method="min", ascending=False) * 500 +
    bottleneck_df["send"].rank(method="min", ascending=False) * 20
)

bottleneck_df = bottleneck_df.sort_values(
    by=["부족량", "send", "설비수"],
    ascending=[False, False, False]
)

with left_col:
    st.markdown("**CAPA 부족량 기준 Top 병목 PRC**")
    st.dataframe(
        bottleneck_df[[
            "prc", "model", "capa", "send", "capa_send_sum", "생산목표", "부족량",
            "설비수", "wpd", "달성여부"
        ]].reset_index(drop=True),
        use_container_width=True
    )

with right_col:
    top10 = bottleneck_df.head(10).sort_values("부족량", ascending=True)

    fig5 = go.Figure()
    fig5.add_trace(
        go.Bar(
            x=top10["부족량"],
            y=top10["prc"],
            orientation="h",
            text=top10["부족량"].apply(fmt_num),
            textposition="outside",
            marker_color="red",
            name="부족량"
        )
    )

    fig5.update_layout(
        title="병목 PRC Top10 (부족량 기준)",
        xaxis_title="부족량",
        yaxis_title="PRC",
        height=500
    )

    st.plotly_chart(fig5, use_container_width=True)

st.divider()

# =========================================================
# 6. SEND vs CAPA Scatter
# =========================================================
st.subheader("6. SEND vs CAPA Scatter")

scatter_df = df_selected.copy()
scatter_df["상태구분"] = scatter_df.apply(
    lambda r: "CAPA 부족" if r["capa"] < target_value else "정상",
    axis=1
)

fig6 = px.scatter(
    scatter_df,
    x="capa",
    y="send",
    size="설비수",
    color="상태구분",
    hover_name="prc",
    hover_data={
        "model": True,
        "생산목표": True,
        "부족량": True,
        "설비수": True,
        "capa": ":,.0f",
        "send": ":,.0f"
    },
    title=f"SEND vs CAPA ({selected_month}, LINE {selected_line}, DR {selected_dr})"
)

fig6.add_vline(
    x=target_value,
    line_width=3,
    line_dash="dash",
    line_color="black",
    annotation_text="생산목표",
    annotation_position="top"
)

fig6.update_layout(
    xaxis_title="CAPA",
    yaxis_title="SEND",
    height=600
)

st.plotly_chart(fig6, use_container_width=True)

st.divider()

# =========================================================
# 7. 월별 PRC CAPA Heatmap
#    - CAPA+SEND와 생산목표 차이 기반
#    - 부족할수록 빨간색, 초과할수록 파란색
# =========================================================
st.subheader("7. 월별 PRC CAPA Heatmap")

heatmap_source = df_line_dr.copy()
heatmap_source["capa_send_sum"] = heatmap_source["capa"] + heatmap_source["send"]
heatmap_source["target_gap_with_send"] = heatmap_source["capa_send_sum"] - heatmap_source["생산목표"]

heatmap_df = heatmap_source.pivot_table(
    index="prc",
    columns="생산월",
    values="target_gap_with_send",
    aggfunc="sum"
)

heatmap_df = heatmap_df.reindex(
    columns=sorted(heatmap_df.columns.tolist(), key=month_sort_key)
)

heatmap_hover = heatmap_source.pivot_table(
    index="prc",
    columns="생산월",
    values="capa_send_sum",
    aggfunc="sum"
).reindex(columns=heatmap_df.columns)

target_hover = heatmap_source.pivot_table(
    index="prc",
    columns="생산월",
    values="생산목표",
    aggfunc="first"
).reindex(columns=heatmap_df.columns)

z_values = heatmap_df.values
zmax = abs(pd.DataFrame(z_values).stack().dropna().max()) if not pd.DataFrame(z_values).stack().dropna().empty else 1
zmin = abs(pd.DataFrame(z_values).stack().dropna().min()) if not pd.DataFrame(z_values).stack().dropna().empty else 1
zabs = max(zmax, zmin)
if zabs == 0:
    zabs = 1

customdata = []
for prc in heatmap_df.index:
    row = []
    for month in heatmap_df.columns:
        row.append([
            heatmap_hover.loc[prc, month] if month in heatmap_hover.columns else None,
            target_hover.loc[prc, month] if month in target_hover.columns else None
        ])
    customdata.append(row)

fig7 = go.Figure(
    data=go.Heatmap(
        z=heatmap_df.values,
        x=heatmap_df.columns,
        y=heatmap_df.index,
        customdata=customdata,
        colorscale=[
            [0.0, "#b30000"],
            [0.2, "#ef5350"],
            [0.5, "#f7f7f7"],
            [0.8, "#64b5f6"],
            [1.0, "#0d47a1"],
        ],
        zmin=-zabs,
        zmax=zabs,
        colorbar=dict(title="(CAPA+SEND)-목표"),
        hovertemplate=(
            "<b>PRC</b>: %{y}<br>"
            "<b>생산월</b>: %{x}<br>"
            "<b>CAPA+SEND</b>: %{customdata[0]:,.0f}<br>"
            "<b>생산목표</b>: %{customdata[1]:,.0f}<br>"
            "<b>차이</b>: %{z:,.0f}<extra></extra>"
        ),
        hoverongaps=False
    )
)

fig7.update_layout(
    title=f"월별 PRC CAPA Heatmap (CAPA+SEND 기준, LINE {selected_line}, DR {selected_dr})",
    xaxis_title="생산월",
    yaxis_title="PRC",
    height=1200
)

st.plotly_chart(fig7, use_container_width=True)

st.divider()

# =========================================================
# 8. 상세 분석 테이블
# =========================================================
st.subheader("8. 상세 분석 테이블")

detail_df = df_selected.copy()
detail_df["목표대비차이"] = detail_df["capa"] - detail_df["생산목표"]
detail_df["(CAPA+SEND)-목표"] = detail_df["capa_send_sum"] - detail_df["생산목표"]
detail_df["SEND/CAPA(%)"] = detail_df["send_capa_ratio"].round(2)

detail_df = detail_df.sort_values(
    by=["부족량", "capa"],
    ascending=[False, True]
)

st.dataframe(
    detail_df[[
        "prc", "model", "dr", "설비수", "wpd", "send",
        "capa", "capa_send_sum", "생산목표", "부족량",
        "목표대비차이", "(CAPA+SEND)-목표",
        "SEND/CAPA(%)", "달성여부"
    ]],
    use_container_width=True
)

# =========================================================
# 원본 데이터
# =========================================================
with st.expander("원본 데이터 보기"):
    st.dataframe(
        df_selected.sort_values(by="prc", ascending=True),
        use_container_width=True
    )