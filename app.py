import streamlit as st
import pandas as pd
import yfinance as yf
from google import genai
from dotenv import load_dotenv
import os

load_dotenv()
gemini_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

st.set_page_config(page_title="포트폴리오 현황", layout="wide")
st.title("주식 포트폴리오 현황")

# 포트폴리오 데이터 로드
df = pd.read_csv("portfolio.csv")

# 고유 종목코드 추출 후 주가 + 환율 조회
tickers = df["종목코드"].unique().tolist()
symbols = tickers + ["USDKRW=X"]


@st.cache_data(ttl=300)
def fetch_prices(symbols):
    data = yf.download(symbols, period="5d", group_by="ticker", progress=False)
    prices = {}
    prev_prices = {}
    for s in symbols:
        try:
            close = data[s]["Close"].dropna()
            prices[s] = float(close.iloc[-1])
            prev_prices[s] = float(close.iloc[-2]) if len(close) >= 2 else None
        except Exception:
            prices[s] = None
            prev_prices[s] = None
    # 최신 데이터 날짜 추출
    try:
        latest_date = data.index[-1].strftime("%Y-%m-%d")
    except Exception:
        latest_date = "-"
    return prices, prev_prices, latest_date


with st.spinner("주가 및 환율 조회 중..."):
    prices, prev_prices, price_date = fetch_prices(symbols)

exchange_rate = prices.pop("USDKRW=X", None)
prev_prices.pop("USDKRW=X", None)
if exchange_rate is None:
    st.error("환율 정보를 불러올 수 없습니다.")
    st.stop()

col_date, col_btn = st.columns([4, 1])
col_date.caption(f"기준일: {price_date}")
if col_btn.button("🔄 새로고침"):
    st.cache_data.clear()
    st.rerun()
st.metric("USD/KRW 환율", f"{exchange_rate:,.2f}원")
st.divider()

# 평가금액 계산
df["현재가($)"] = df["종목코드"].map(prices)
df["전일가($)"] = df["종목코드"].map(prev_prices)
df["전일대비($)"] = df["현재가($)"] - df["전일가($)"]
df["전일대비(%)"] = (df["전일대비($)"] / df["전일가($)"]) * 100
df["평가금액($)"] = df["수량"] * df["현재가($)"]
df["평가금액(원)"] = df["평가금액($)"] * exchange_rate
df["평가손익(원)"] = df["손익단가(원)"] * df["수량"]
df["매입금액(원)"] = df["평가금액(원)"] - df["평가손익(원)"]
df["수익률(원)"] = (df["평가손익(원)"] / df["매입금액(원)"]) * 100
df["매입금액($)"] = df["매입금액(원)"] / exchange_rate
df["평가손익($)"] = df["평가금액($)"] - df["매입금액($)"]
df["수익률($)"] = (df["평가손익($)"] / df["매입금액($)"]) * 100

# 1) 합산 요약 (2행 3열)
owners = df["보유자"].unique().tolist()
col_total, *col_owners = st.columns(len(owners) + 1)

def calc_return(sub):
    total_eval = sub["평가금액(원)"].sum()
    total_cost = sub["매입금액(원)"].sum()
    total_pnl = sub["평가손익(원)"].sum()
    pct = (total_pnl / total_cost) * 100 if total_cost != 0 else 0
    return total_eval, total_pnl, pct

t_eval, t_pnl, t_pct = calc_return(df)
with col_total:
    st.markdown("**전체**")
    st.metric("USD", f"${df['평가금액($)'].sum():,.2f}")
    st.metric("KRW", f"{df['평가금액(원)'].sum():,.0f}원")
    st.metric("평가손익", f"{t_pnl:+,.0f}원")
    color = "red" if t_pct > 0 else "blue" if t_pct < 0 else "inherit"
    st.markdown(f"수익률 <span style='color:{color}'>{t_pct:+.2f}%</span>", unsafe_allow_html=True)

for i, name in enumerate(owners):
    sub = df[df["보유자"] == name]
    s_eval, s_pnl, s_pct = calc_return(sub)
    with col_owners[i]:
        st.markdown(f"**{name}**")
        st.metric("USD", f"${sub['평가금액($)'].sum():,.2f}")
        st.metric("KRW", f"{s_eval:,.0f}원")
        st.metric("평가손익", f"{s_pnl:+,.0f}원")
        color = "red" if s_pct > 0 else "blue" if s_pct < 0 else "inherit"
        st.markdown(f"수익률 <span style='color:{color}'>{s_pct:+.2f}%</span>", unsafe_allow_html=True)
st.divider()

# 3) 전체 종목 통합 테이블
st.subheader("보유 종목 상세")
display = df[["보유자", "종목코드", "종목명", "수량", "현재가($)", "전일대비(%)",
              "평가금액(원)", "평가손익(원)", "수익률(원)"]].copy()


def color_change(val):
    if pd.isna(val):
        return ""
    if val > 0:
        return "color: red"
    elif val < 0:
        return "color: blue"
    return ""


color_cols = ["전일대비(%)", "평가손익(원)", "수익률(원)"]

styled = (
    display.style
    .applymap(color_change, subset=color_cols)
    .format({
        "현재가($)": lambda x: f"{x:,.2f}" if pd.notna(x) else "-",
        "전일대비(%)": lambda x: f"{x:+,.2f}%" if pd.notna(x) else "-",
        "평가금액(원)": lambda x: f"{x:,.0f}" if pd.notna(x) else "-",
        "평가손익(원)": lambda x: f"{x:+,.0f}" if pd.notna(x) else "-",
        "수익률(원)": lambda x: f"{x:+,.2f}%" if pd.notna(x) else "-",
    })
)

st.dataframe(styled, use_container_width=True, hide_index=True, height=(len(display) + 1) * 35 + 3)

# 4) 종목별 뉴스
st.divider()
st.subheader("종목별 뉴스")


@st.cache_data(ttl=600)
def fetch_news(ticker):
    t = yf.Ticker(ticker)
    return t.news or []


@st.cache_data(ttl=600)
def translate_news_batch(news_texts):
    """뉴스 여러 건을 한 번의 API 호출로 번역+요약"""
    if not news_texts:
        return []
    prompt = (
        "아래 영문 뉴스들을 각각 한국어로 번역하고 요약해줘.\n"
        "각 뉴스마다 아래 형식으로 출력해:\n"
        "[N]\n제목: (번역된 제목)\n요약: (본문을 2~3문장으로 번역+요약)\n\n"
    )
    for i, (title, summary) in enumerate(news_texts):
        prompt += f"[{i+1}]\nTitle: {title}\nBody: {summary}\n\n"

    try:
        resp = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = resp.text.strip()
        results = []
        blocks = text.split("[")[1:]  # [1], [2], ...
        for block in blocks:
            title_kr = ""
            summary_kr = ""
            for line in block.split("\n"):
                if line.startswith("제목:"):
                    title_kr = line[len("제목:"):].strip()
                elif line.startswith("요약:"):
                    summary_kr = line[len("요약:"):].strip()
            results.append((title_kr, summary_kr))
        return results
    except Exception as e:
        st.warning(f"번역 실패 (API 할당량 초과 가능): {e}")
        return [(t, s) for t, s in news_texts]


# 전일대비 등락률 순으로 드롭다운 정렬
ticker_change = (
    df[["종목코드", "종목명", "전일대비(%)"]]
    .drop_duplicates(subset="종목코드")
    .sort_values("전일대비(%)", ascending=False)
)
ticker_list = ticker_change["종목코드"].tolist()
ticker_names = dict(zip(ticker_change["종목코드"], ticker_change["종목명"]))
ticker_changes = dict(zip(ticker_change["종목코드"], ticker_change["전일대비(%)"]))

selected = st.selectbox(
    "종목 선택",
    [None] + ticker_list,
    format_func=lambda x: "종목을 선택하세요" if x is None else f"{x} ({ticker_names[x]}) {ticker_changes[x]:+.2f}%",
)

if selected:
    news_list = fetch_news(selected)
    if not news_list:
        st.info("뉴스가 없습니다.")
    else:
        items = news_list[:5]
        news_texts = []
        meta = []
        for item in items:
            content = item.get("content", {})
            news_texts.append((content.get("title", ""), content.get("summary", "")))
            meta.append({
                "pub_date": content.get("pubDate", "")[:10],
                "provider": content.get("provider", {}).get("displayName", ""),
                "url": content.get("canonicalUrl", {}).get("url", ""),
            })

        translated = translate_news_batch(tuple(tuple(x) for x in news_texts))

        for i, m in enumerate(meta):
            if i < len(translated):
                title_kr, summary_kr = translated[i]
            else:
                title_kr, summary_kr = news_texts[i]
            with st.container():
                st.markdown(f"**{title_kr}**")
                if summary_kr:
                    st.caption(summary_kr)
                st.caption(f"{m['pub_date']} | {m['provider']} | [원문]({m['url']})")
                st.markdown("---")
