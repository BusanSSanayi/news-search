import streamlit as st
import pandas as pd
import json
import re
from google import genai
from google.genai import types
from supabase import create_client, Client

# 1. 페이지 설정
st.set_page_config(page_title="AI 뉴스 검색 & 자동 저장", layout="wide")

# 2. 시크릿 관리 및 클라이언트 초기화
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except KeyError as e:
    st.error(f"Secret 설정이 필요합니다: {e}")
    st.stop()

# 클라이언트 초기화
genai_client = genai.Client(api_key=GEMINI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3. 화면 구성 (3개의 탭)
tab1, tab2, tab3 = st.tabs(["🔍 검색하기", "💾 저장된 뉴스 보기", "📊 통계 분석"])

# --- Tab 1: 검색 및 저장 ---
with tab1:
    st.header("최신 뉴스 검색")
    keyword = st.text_input("검색어를 입력하세요 (예: 엔비디아 실적, 양자 컴퓨터)", "")
    search_btn = st.button("뉴스 검색 및 자동 저장")

    if search_btn and keyword:
        with st.spinner("AI가 최신 뉴스를 검색하고 분석 중입니다..."):
            try:
                # Gemini 호출 (Google 검색 도구 활성화)
                # 주의: 검색 도구 사용 시 response_mime_type="application/json"을 동시에 쓸 수 없어 프롬프트로 제어
                prompt = f"""
                키워드 '{keyword}'에 대한 가장 최신 뉴스 딱 **2건**만 검색해. 
                결과는 반드시 아래의 JSON 배열 형식으로만 응답해. 절대 다른 설명은 하지 마.
                절대 URL을 지어내지 마(환각 방지).

                JSON 형식 예시:
                [
                  {{
                    "title": "뉴스 제목",
                    "source": "언론사명",
                    "news_date": "YYYY-MM-DD",
                    "url": "실제 뉴스 URL",
                    "summary": "뉴스 요약 내용"
                  }}
                ]
                """
                
                response = genai_client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearchRetrieval())],
                        temperature=0.0
                    )
                )

                # JSON 문자열 추출 (마크다운 코드 블록 제거)
                res_text = response.text
                json_match = re.search(r'\[.*\]', res_text, re.DOTALL)
                
                if json_match:
                    news_data = json.loads(json_match.group())
                    
                    # 데이터 처리 및 DB 저장
                    for item in news_data:
                        item['keyword'] = keyword # 키워드 추가
                        
                        # Supabase Upsert (url이 유니크하므로 중복 시 업데이트 처리)
                        try:
                            supabase.table("news_history").upsert(item, on_conflict="url").execute()
                            st.success(f"저장 완료: {item['title']}")
                        except Exception as e:
                            st.warning(f"저장 중 오류 혹은 중복 데이터: {item['title']}")

                    st.json(news_data)
                else:
                    st.error("뉴스 형식을 파싱할 수 없습니다. 다시 시도해 주세요.")
                    st.write("응답 원문:", res_text)

            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

# --- Tab 2: 저장된 뉴스 보기 ---
with tab2:
    st.header("저장된 뉴스 목록")
    if st.button("데이터 불러오기"):
        res = supabase.table("news_history").select("*").order("created_at", descending=True).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            # URL을 클릭 가능한 링크로 변환하여 출력
            st.dataframe(df, column_config={
                "url": st.column_config.LinkColumn("뉴스 링크")
            }, use_container_width=True)
        else:
            st.info("저장된 데이터가 없습니다.")

# --- Tab 3: 통계 분석 ---
with tab3:
    st.header("검색 통계")
    res = supabase.table("news_history").select("keyword, source").execute()
    if res.data:
        df_stats = pd.DataFrame(res.data)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("키워드별 검색 횟수")
            st.bar_chart(df_stats['keyword'].value_counts())
            
        with col2:
            st.subheader("언론사별 뉴스 비중")
            st.write(df_stats['source'].value_counts())
    else:
        st.info("분석할 데이터가 부족합니다.")