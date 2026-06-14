import streamlit as st
import pandas as pd
from verifier import run_verification
from parser import load_checklist_from_file
from app_logging import setup_logging
import json

setup_logging()

st.set_page_config(
    page_title="Compliance Verification Studio",
    page_icon="CV",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at 18% 0%, rgba(59, 130, 246, 0.22), transparent 30rem),
            radial-gradient(circle at 88% 10%, rgba(14, 165, 233, 0.16), transparent 28rem),
            linear-gradient(180deg, #020617 0%, #0f172a 48%, #111827 100%);
        color: #e5e7eb;
    }
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 3rem;
        max-width: 1180px;
    }
    .hero {
        padding: 2.1rem 2.2rem;
        border-radius: 28px;
        background:
            linear-gradient(135deg, rgba(15, 23, 42, 0.98) 0%, rgba(30, 64, 175, 0.88) 58%, rgba(37, 99, 235, 0.94) 100%);
        color: white;
        margin-bottom: 1.7rem;
        box-shadow: 0 26px 70px rgba(0, 0, 0, 0.42);
        border: 1px solid rgba(255, 255, 255, 0.16);
    }
    .hero h1 {
        margin-bottom: 0.35rem;
        font-size: 2.75rem;
        line-height: 1.05;
        letter-spacing: -0.045em;
    }
    .hero p {
        color: #dbeafe;
        font-size: 1.03rem;
        max-width: 760px;
        margin-bottom: 0;
    }
    .premium-card {
        padding: 1.05rem 1.15rem;
        border-radius: 22px;
        border: 1px solid rgba(148, 163, 184, 0.20);
        background: linear-gradient(180deg, rgba(30, 41, 59, 0.92), rgba(15, 23, 42, 0.92));
        box-shadow: 0 18px 45px rgba(0, 0, 0, 0.24);
        backdrop-filter: blur(14px);
        min-height: 150px;
    }
    .premium-card h3 {
        margin-top: 0.25rem;
        margin-bottom: 0.35rem;
        color: #f8fafc;
        font-size: 1.05rem;
    }
    .premium-card p {
        color: #cbd5e1;
        margin-bottom: 0;
        font-size: 0.93rem;
    }
    .card-kpi {
        color: #2563eb;
        font-size: 1.8rem;
        font-weight: 800;
        letter-spacing: -0.04em;
    }
    .section-label {
        color: #93c5fd;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.3rem;
    }
    .score-pass {
        color: #34d399;
        font-weight: 700;
    }
    .score-warn {
        color: #fbbf24;
        font-weight: 700;
    }
    .score-fail {
        color: #fb7185;
        font-weight: 700;
    }
    h1, h2, h3, h4, h5, h6,
    div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stMarkdownContainer"] li,
    div[data-testid="stCaptionContainer"],
    label {
        color: #e5e7eb !important;
    }
    div[data-testid="stMetricValue"] {
        color: #f8fafc;
        font-size: 2rem;
        font-weight: 800;
    }
    div[data-testid="stMetricLabel"] {
        color: #94a3b8;
    }
    div[data-testid="metric-container"] {
        background: linear-gradient(180deg, rgba(30, 41, 59, 0.88), rgba(15, 23, 42, 0.88));
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-radius: 20px;
        padding: 1rem 1.1rem;
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.22);
    }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
    }
    div[data-testid="stSidebar"] * {
        color: #e5e7eb;
    }
    div[data-testid="stSidebar"] label,
    div[data-testid="stSidebar"] p {
        color: #cbd5e1 !important;
    }
    div[data-testid="stFileUploader"] section {
        border-radius: 18px;
        border: 1px dashed rgba(96, 165, 250, 0.65);
        background: rgba(15, 23, 42, 0.38);
    }
    .stButton > button {
        border-radius: 999px;
        font-weight: 700;
        min-height: 3rem;
    }
    div[data-testid="stTabs"] button {
        color: #cbd5e1;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #60a5fa;
    }
    div[data-testid="stAlert"] {
        background: rgba(30, 41, 59, 0.92);
        border: 1px solid rgba(96, 165, 250, 0.28);
        color: #e5e7eb;
    }
    div[data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.76);
        border: 1px solid rgba(148, 163, 184, 0.20);
        border-radius: 18px;
    }
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(148, 163, 184, 0.20);
        border-radius: 16px;
        overflow: hidden;
    }
    .stDownloadButton > button {
        border-radius: 999px;
        border: 1px solid rgba(96, 165, 250, 0.45);
        background: rgba(15, 23, 42, 0.78);
        color: #e5e7eb;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def score_class(score):
    if score >= 80:
        return "score-pass"
    if score >= 50:
        return "score-warn"
    return "score-fail"


def status_help(score):
    if score >= 90:
        return "Excellent control coverage with minimal compliance gaps."
    if score >= 80:
        return "Strong result, but review any remaining exceptions."
    if score >= 65:
        return "Moderate result. Several checks require review."
    if score >= 50:
        return "High-risk result. Missing evidence should be addressed."
    return "Critical result. The document does not satisfy key requirements."


def cell_to_display(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return value


def display_df(df):
    if df is None or df.empty:
        return df
    safe_df = df.copy()
    for col in safe_df.columns:
        if safe_df[col].dtype == "object":
            safe_df[col] = safe_df[col].map(cell_to_display)
    return safe_df


def render_empty_state():
    st.markdown("### Verification Command Center")
    left, middle, right = st.columns(3)
    with left:
        st.markdown(
            """
            <div class="premium-card">
                <div class="card-kpi">01</div>
                <h3>Upload Policy Checklist</h3>
                <p>Load weighted controls, thresholds, evidence expectations, and categories from CSV, Excel, or JSON.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with middle:
        st.markdown(
            """
            <div class="premium-card">
                <div class="card-kpi">02</div>
                <h3>Analyze Evidence</h3>
                <p>Parse documents, detect fields, evaluate numeric thresholds, and optionally run OpenAI audit reasoning.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            """
            <div class="premium-card">
                <div class="card-kpi">03</div>
                <h3>Export Audit Report</h3>
                <p>Review executive scores, risk ratings, category performance, LLM reasoning, logs, and downloadable reports.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.info("Upload files from the sidebar to start a verification run.")


st.markdown(
    """
    <div class="hero">
        <div class="section-label">Enterprise Compliance Intelligence</div>
        <h1>Checklist Verification Control Room</h1>
        <p>
            A portfolio-grade verification system for policy checklists, evidence review,
            weighted scoring, risk analytics, LLM-assisted audit reasoning, and traceable run logs.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar settings ---
st.sidebar.header("Verification Settings")
use_llm = st.sidebar.toggle("Enable OpenAI reasoning", value=False)
llm_model = st.sidebar.selectbox(
    "OpenAI model",
    ["gpt-4o", "gpt-4.1", "gpt-4o-mini"],
    index=0,
    disabled=not use_llm,
)
st.sidebar.caption(
    "GPT-4o is the default because it works reliably with this setup. GPT-4.1 is also available for stronger reasoning."
)
st.sidebar.divider()
show_logs = st.sidebar.toggle("Show run logs", value=True)
st.sidebar.caption("Logs appear in the Run Logs tab and in the terminal where Streamlit is running.")
st.sidebar.divider()
st.sidebar.markdown("**Scoring Method**")
st.sidebar.caption(
    "Each checklist item receives PASS, PARTIAL, or FAIL. Document scores are weighted by the checklist weight column and grouped into risk ratings."
)
st.sidebar.divider()
st.sidebar.markdown("### Verification Package")
checklist_file = st.sidebar.file_uploader(
    "Checklist file",
    type=["csv", "xlsx", "xls", "json"],
    help="Expected columns: id, item_text, category, weight, rule_type, rule_spec, confidence_threshold.",
)
support_files = st.sidebar.file_uploader(
    "Evidence documents",
    type=["pdf", "txt"],
    accept_multiple_files=True,
    help="TXT works immediately. PDFs can use text extraction and OCR if configured.",
)
st.sidebar.caption("Tip: use files from `test_data` for a full demo run.")
run_button = st.sidebar.button("Run Verification", type="primary", width="stretch")

if not run_button:
    render_empty_state()

if run_button:
    if not checklist_file or not support_files:
        st.error("Please upload at least a checklist and one supporting document.")
        st.stop()

    with st.spinner("Parsing documents, applying checklist rules, and building the report..."):
        checklist_df = load_checklist_from_file(checklist_file)
        rules_df = pd.DataFrame(columns=['id', 'check_id', 'rule_type', 'rule_spec', 'confidence_threshold'])
        result = run_verification(
            checklist_df,
            rules_df,
            support_files,
            use_llm=use_llm,
            llm_model=llm_model,
        )

    overall_score = result["overall_score"]
    st.markdown("## Executive Summary")
    score_col, risk_col, checks_col, model_col = st.columns(4)
    total_checks = sum(doc.get("checks", 0) for doc in result["documents"])
    total_failed = sum(doc.get("failed", 0) for doc in result["documents"])
    with score_col:
        st.metric("Overall Score", f"{overall_score}/100", help=status_help(overall_score))
    with risk_col:
        st.metric("Risk Rating", result["overall_risk"])
    with checks_col:
        st.metric("Checks Evaluated", total_checks, delta=f"{total_failed} failed")
    with model_col:
        st.metric("Reasoning Mode", result["llm_model"])

    st.markdown(
        f"<p class='{score_class(overall_score)}'>Overall rating: {result['overall_status']}.</p>",
        unsafe_allow_html=True,
    )
    if use_llm and result.get("llm_error_count", 0):
        st.warning(
            f"OpenAI reasoning failed for {result['llm_error_count']} check(s). "
            "The compliance score uses the rule-based result for those checks."
        )

    summary_tab, analytics_tab, documents_tab, logs_tab, export_tab = st.tabs(
        ["Summary", "Analytics", "Document Review", "Run Logs", "Export"]
    )

    with summary_tab:
        st.subheader("Document Scorecard")
        summary_df = result["summary_table"]
        st.dataframe(display_df(summary_df), width="stretch", hide_index=True)

        if not summary_df.empty:
            chart_df = summary_df[["Document", "Score"]].set_index("Document")
            st.bar_chart(chart_df)

    with analytics_tab:
        st.subheader("Compliance Analytics")
        category_df = result.get("category_summary", pd.DataFrame())
        chart_left, chart_right = st.columns(2)

        with chart_left:
            st.markdown("#### Category Scores")
            if category_df is not None and not category_df.empty:
                st.bar_chart(category_df[["category", "score"]].set_index("category"))
                st.dataframe(display_df(category_df), width="stretch", hide_index=True)
            else:
                st.info("No category data available.")

        with chart_right:
            st.markdown("#### Outcome Distribution")
            status_rows = []
            for doc in result["documents"]:
                status_rows.extend([
                    {"status": "PASS", "count": doc.get("passed", 0)},
                    {"status": "PARTIAL", "count": doc.get("partial", 0)},
                    {"status": "FAIL", "count": doc.get("failed", 0)},
                ])
            status_df = pd.DataFrame(status_rows).groupby("status", as_index=False)["count"].sum()
            st.bar_chart(status_df.set_index("status"))
            st.dataframe(display_df(status_df), width="stretch", hide_index=True)

    with documents_tab:
        st.subheader("Detailed Document Review")
        for doc in result["documents"]:
            with st.expander(f"{doc['name']} | Score {doc['score']}/100 | {doc['risk']} Risk", expanded=True):
                doc_metric_cols = st.columns(5)
                doc_metric_cols[0].metric("Score", f"{doc['score']}/100")
                doc_metric_cols[1].metric("Passed", doc["passed"])
                doc_metric_cols[2].metric("Partial", doc["partial"])
                doc_metric_cols[3].metric("Failed", doc["failed"])
                doc_metric_cols[4].metric("Fields Detected", doc["fields_detected"])

                findings_tab, categories_tab, llm_tab = st.tabs(["Findings", "Categories", "LLM Reasoning"])
                df = pd.DataFrame(doc['items'])

                with findings_tab:
                    display_cols = [
                        'status',
                        'score',
                        'check_id',
                        'item_text',
                        'category',
                        'rule_type',
                        'confidence',
                        'expected',
                        'actual',
                        'explanation',
                        'reason_code',
                    ]
                    existing_cols = [col for col in display_cols if col in df.columns]
                    st.dataframe(display_df(df[existing_cols]), width="stretch", hide_index=True)

                with categories_tab:
                    doc_category_df = pd.DataFrame(doc.get("category_scores", []))
                    if not doc_category_df.empty:
                        st.bar_chart(doc_category_df[["category", "score"]].set_index("category"))
                        st.dataframe(display_df(doc_category_df), width="stretch", hide_index=True)
                    else:
                        st.info("No category scores available for this document.")

                with llm_tab:
                    if use_llm:
                        llm_cols = [
                            'status',
                            'check_id',
                            'item_text',
                            'llm_outcome',
                            'llm_confidence',
                            'llm_error',
                            'llm_explanation',
                            'llm_evidence',
                            'llm_missing_info',
                            'llm_recommendation',
                        ]
                        existing_llm_cols = [col for col in llm_cols if col in df.columns]
                        st.dataframe(display_df(df[existing_llm_cols]), width="stretch", hide_index=True)
                    else:
                        st.info("OpenAI reasoning was not enabled for this run.")

                csv_data = df.to_csv(index=False).encode('utf-8')
                json_data = json.dumps(doc, indent=2, default=str).encode("utf-8")
                download_left, download_right = st.columns(2)
                with download_left:
                    st.download_button(
                        label=f"Download {doc['name']} Findings CSV",
                        data=csv_data,
                        file_name=f"{doc['name']}_verification.csv",
                        mime="text/csv",
                        width="stretch",
                    )
                with download_right:
                    st.download_button(
                        label=f"Download {doc['name']} Report JSON",
                        data=json_data,
                        file_name=f"{doc['name']}_report.json",
                        mime="application/json",
                        width="stretch",
                    )

    with logs_tab:
        st.subheader("Run Logs")
        run_log = result.get("run_log", "")
        if run_log:
            log_filter = st.selectbox(
                "Filter",
                ["All", "INFO", "WARNING", "ERROR", "OpenAI", "Rule evaluated", "Document"],
                label_visibility="collapsed",
            )
            filtered_lines = run_log.splitlines()
            if log_filter != "All":
                needle = log_filter.upper() if log_filter in {"INFO", "WARNING", "ERROR"} else log_filter
                filtered_lines = [line for line in filtered_lines if needle in line]

            st.caption(f"{len(filtered_lines)} log line(s)")
            st.code("\n".join(filtered_lines) if filtered_lines else "No matching log lines.", language="text")
            st.download_button(
                label="Download run_log.txt",
                data=run_log.encode("utf-8"),
                file_name="compliance_verification_run_log.txt",
                mime="text/plain",
                width="stretch",
            )
        else:
            st.info("No logs captured for this run.")

    with export_tab:
        st.subheader("Export Audit Package")
        export_payload = {
            "overall_score": result.get("overall_score"),
            "overall_status": result.get("overall_status"),
            "overall_risk": result.get("overall_risk"),
            "llm_model": result.get("llm_model"),
            "llm_error_count": result.get("llm_error_count"),
            "run_log": result.get("run_log"),
            "documents": result.get("documents", []),
        }
        st.download_button(
            label="Download Complete Report JSON",
            data=json.dumps(export_payload, indent=2, default=str).encode("utf-8"),
            file_name="compliance_verification_report.json",
            mime="application/json",
            width="stretch",
        )
        st.caption("The JSON report includes scores, findings, category summaries, LLM reasoning, and export-ready audit details.")
