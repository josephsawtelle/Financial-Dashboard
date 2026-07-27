from __future__ import annotations

from io import BytesIO
from typing import Dict, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Small Business Financial Dashboard",
    page_icon="📊",
    layout="wide",
)

REQUIRED_TRANSACTION_COLUMNS = {
    "Date",
    "Type",
    "Category",
    "Customer / Project",
    "Amount ($)",
    "Payment Status",
}

TRANSACTION_ALIASES = {
    "date": "Date",
    "transaction date": "Date",
    "type": "Type",
    "transaction type": "Type",
    "category": "Category",
    "customer": "Customer / Project",
    "project": "Customer / Project",
    "customer / project": "Customer / Project",
    "amount": "Amount ($)",
    "amount ($)": "Amount ($)",
    "payment status": "Payment Status",
    "status": "Payment Status",
    "description": "Description",
    "transaction id": "Transaction ID",
    "invoice / ref #": "Invoice / Ref #",
    "invoice": "Invoice / Ref #",
    "notes": "Notes",
}


def money(value: float) -> str:
    return f"${value:,.0f}"


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = [str(c).strip() for c in cleaned.columns]
    rename_map = {}
    for column in cleaned.columns:
        alias = TRANSACTION_ALIASES.get(column.lower())
        if alias:
            rename_map[column] = alias
    return cleaned.rename(columns=rename_map)


def read_template_excel(file_bytes: bytes) -> Tuple[pd.DataFrame, pd.DataFrame]:
    excel = pd.ExcelFile(BytesIO(file_bytes))
    if "Transactions" not in excel.sheet_names:
        raise ValueError("The workbook must contain a sheet named 'Transactions'.")

    transactions = pd.read_excel(excel, sheet_name="Transactions", header=1)
    transactions = normalize_columns(transactions)

    if "A_R Tracker" in excel.sheet_names:
        ar = pd.read_excel(excel, sheet_name="A_R Tracker", header=1)
        ar.columns = [str(c).strip() for c in ar.columns]
    else:
        ar = pd.DataFrame()

    return transactions, ar


def read_uploaded_file(uploaded_file) -> Tuple[pd.DataFrame, pd.DataFrame]:
    file_bytes = uploaded_file.getvalue()
    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        transactions = pd.read_csv(BytesIO(file_bytes))
        return normalize_columns(transactions), pd.DataFrame()

    return read_template_excel(file_bytes)


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned = cleaned.dropna(how="all")

    missing = REQUIRED_TRANSACTION_COLUMNS.difference(cleaned.columns)
    if missing:
        raise ValueError(
            "Missing required columns: " + ", ".join(sorted(missing))
        )

    cleaned["Date"] = pd.to_datetime(cleaned["Date"], errors="coerce")
    cleaned["Amount ($)"] = pd.to_numeric(cleaned["Amount ($)"], errors="coerce")
    cleaned["Type"] = cleaned["Type"].astype("string").str.strip().str.title()
    cleaned["Category"] = cleaned["Category"].astype("string").str.strip()
    cleaned["Customer / Project"] = (
        cleaned["Customer / Project"].astype("string").str.strip()
    )
    cleaned["Payment Status"] = (
        cleaned["Payment Status"].astype("string").str.strip().str.title()
    )

    cleaned["Revenue ($)"] = cleaned["Amount ($)"].where(
        cleaned["Type"].eq("Revenue"), 0
    )
    cleaned["Expense ($)"] = cleaned["Amount ($)"].where(
        cleaned["Type"].eq("Expense"), 0
    )
    cleaned["Net Cash Flow ($)"] = cleaned["Revenue ($)"] - cleaned["Expense ($)"]
    cleaned["Month"] = cleaned["Date"].dt.to_period("M").dt.to_timestamp()

    missing_core = (
        cleaned["Date"].isna()
        | cleaned["Amount ($)"].isna()
        | ~cleaned["Type"].isin(["Revenue", "Expense"])
        | cleaned["Category"].isna()
    )
    revenue_missing_status = cleaned["Type"].eq("Revenue") & cleaned[
        "Payment Status"
    ].isna()
    cleaned["Needs Review?"] = (missing_core | revenue_missing_status).map(
        {True: "Yes", False: "No"}
    )
    return cleaned


def clean_ar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    cleaned = df.dropna(how="all").copy()
    for column in ["Invoice Date", "Due Date", "Expected Collection Date"]:
        if column in cleaned.columns:
            cleaned[column] = pd.to_datetime(cleaned[column], errors="coerce")

    for column in ["Original Amount ($)", "Amount Paid ($)", "Balance Due ($)"]:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce").fillna(0)

    if {"Original Amount ($)", "Amount Paid ($)"}.issubset(cleaned.columns):
        cleaned["Balance Due ($)"] = (
            cleaned["Original Amount ($)"] - cleaned["Amount Paid ($)"]
        ).clip(lower=0)

    today = pd.Timestamp.today().normalize()
    if "Invoice Date" in cleaned.columns:
        cleaned["Days Outstanding"] = (today - cleaned["Invoice Date"]).dt.days.clip(lower=0)

    if {"Balance Due ($)", "Due Date"}.issubset(cleaned.columns):
        cleaned["Status"] = "Sent"
        cleaned.loc[cleaned["Balance Due ($)"].eq(0), "Status"] = "Paid"
        cleaned.loc[
            cleaned["Balance Due ($)"].gt(0) & cleaned["Due Date"].lt(today),
            "Status",
        ] = "Overdue"
        if "Amount Paid ($)" in cleaned.columns:
            cleaned.loc[
                cleaned["Balance Due ($)"].gt(0)
                & cleaned["Amount Paid ($)"].gt(0)
                & cleaned["Due Date"].ge(today),
                "Status",
            ] = "Partial"
    return cleaned


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Dashboard filters")

    valid_dates = df["Date"].dropna()
    if valid_dates.empty:
        return df

    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()
    date_range = st.sidebar.date_input(
        "Transaction dates",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    customers = sorted(
        x for x in df["Customer / Project"].dropna().unique().tolist() if x != "<NA>"
    )
    selected_customers = st.sidebar.multiselect(
        "Customers / projects", customers, default=[]
    )

    categories = sorted(
        x for x in df["Category"].dropna().unique().tolist() if x != "<NA>"
    )
    selected_categories = st.sidebar.multiselect("Categories", categories, default=[])

    filtered = df.copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = map(pd.Timestamp, date_range)
        filtered = filtered[filtered["Date"].between(start_date, end_date)]
    if selected_customers:
        filtered = filtered[filtered["Customer / Project"].isin(selected_customers)]
    if selected_categories:
        filtered = filtered[filtered["Category"].isin(selected_categories)]
    return filtered


def calculate_kpis(transactions: pd.DataFrame, ar: pd.DataFrame) -> Dict[str, float]:
    revenue = transactions["Revenue ($)"].sum()
    expenses = transactions["Expense ($)"].sum()
    net = revenue - expenses
    margin = net / revenue if revenue else 0

    unpaid = transactions.loc[
        transactions["Type"].eq("Revenue")
        & ~transactions["Payment Status"].eq("Paid"),
        "Revenue ($)",
    ].sum()

    outstanding_ar = ar["Balance Due ($)"].sum() if "Balance Due ($)" in ar.columns else unpaid
    overdue = (
        int(ar["Status"].eq("Overdue").sum()) if "Status" in ar.columns else 0
    )

    return {
        "Revenue": revenue,
        "Expenses": expenses,
        "Net Cash Flow": net,
        "Profit Margin": margin,
        "Outstanding A/R": outstanding_ar,
        "Overdue Invoices": overdue,
    }


def downloadable_excel(transactions: pd.DataFrame, ar: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        transactions.to_excel(writer, sheet_name="Clean Transactions", index=False)
        if not ar.empty:
            ar.to_excel(writer, sheet_name="Clean A_R", index=False)
    return output.getvalue()


st.title("Small Business Financial Dashboard")
st.caption(
    "Upload the standardized Excel template or a CSV containing transaction data. "
    "The app processes the file locally during your session and builds an interactive dashboard."
)

with st.expander("Required transaction fields", expanded=False):
    st.write(
        "Date, Type, Category, Customer / Project, Amount ($), and Payment Status. "
        "The provided Excel template already uses these names."
    )

uploaded_file = st.file_uploader(
    "Upload an Excel or CSV file",
    type=["xlsx", "xls", "csv"],
    help="The Excel template should contain the Transactions sheet and may contain A_R Tracker.",
)

if uploaded_file is None:
    st.info("Upload the sample workbook or a completed client workbook to begin.")
    st.stop()

try:
    raw_transactions, raw_ar = read_uploaded_file(uploaded_file)
    transactions = clean_transactions(raw_transactions)
    ar = clean_ar(raw_ar)
except Exception as exc:
    st.error(f"The file could not be processed: {exc}")
    st.stop()

filtered = apply_filters(transactions)
kpis = calculate_kpis(filtered, ar)

st.success(
    f"Loaded {len(transactions):,} transactions"
    + (f" and {len(ar):,} invoices." if not ar.empty else ".")
)

row1 = st.columns(4)
row1[0].metric("Revenue", money(kpis["Revenue"]))
row1[1].metric("Expenses", money(kpis["Expenses"]))
row1[2].metric("Net cash flow", money(kpis["Net Cash Flow"]))
row1[3].metric("Profit margin", f"{kpis['Profit Margin']:.1%}")

row2 = st.columns(3)
row2[0].metric("Outstanding A/R", money(kpis["Outstanding A/R"]))
row2[1].metric("Overdue invoices", f"{kpis['Overdue Invoices']:,}")
row2[2].metric(
    "Transactions needing review",
    f"{int(filtered['Needs Review?'].eq('Yes').sum()):,}",
)

monthly = (
    filtered.groupby("Month", as_index=False)[["Revenue ($)", "Expense ($)"]]
    .sum()
    .sort_values("Month")
)
monthly["Net Cash Flow ($)"] = monthly["Revenue ($)"] - monthly["Expense ($)"]

left, right = st.columns(2)
with left:
    st.subheader("Monthly performance")
    if not monthly.empty:
        monthly_long = monthly.melt(
            id_vars="Month",
            value_vars=["Revenue ($)", "Expense ($)", "Net Cash Flow ($)"],
            var_name="Metric",
            value_name="Amount",
        )
        fig = px.line(monthly_long, x="Month", y="Amount", color="Metric", markers=True)
        fig.update_layout(yaxis_tickprefix="$", legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No transactions match the selected filters.")

with right:
    st.subheader("Expense mix")
    expense_mix = (
        filtered.loc[filtered["Expense ($)"].gt(0)]
        .groupby("Category", as_index=False)["Expense ($)"]
        .sum()
        .sort_values("Expense ($)", ascending=True)
    )
    if not expense_mix.empty:
        fig = px.bar(expense_mix, x="Expense ($)", y="Category", orientation="h")
        fig.update_layout(xaxis_tickprefix="$", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No expense data matches the selected filters.")

left, right = st.columns(2)
with left:
    st.subheader("Revenue by customer or project")
    customer_revenue = (
        filtered.loc[filtered["Revenue ($)"].gt(0)]
        .groupby("Customer / Project", as_index=False)["Revenue ($)"]
        .sum()
        .sort_values("Revenue ($)", ascending=False)
        .head(12)
    )
    if not customer_revenue.empty:
        fig = px.bar(customer_revenue, x="Customer / Project", y="Revenue ($)")
        fig.update_layout(yaxis_tickprefix="$", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No customer revenue matches the selected filters.")

with right:
    st.subheader("Accounts receivable aging")
    if not ar.empty and {"Balance Due ($)", "Days Outstanding"}.issubset(ar.columns):
        open_ar = ar.loc[ar["Balance Due ($)"].gt(0)].copy()
        open_ar["Aging Bucket"] = pd.cut(
            open_ar["Days Outstanding"],
            bins=[-1, 30, 60, 90, float("inf")],
            labels=["0–30 days", "31–60 days", "61–90 days", "91+ days"],
        )
        aging = open_ar.groupby("Aging Bucket", observed=False, as_index=False)[
            "Balance Due ($)"
        ].sum()
        fig = px.bar(aging, x="Aging Bucket", y="Balance Due ($)")
        fig.update_layout(yaxis_tickprefix="$", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Upload the A_R Tracker sheet to display receivables aging.")

st.subheader("Data-quality review")
review = transactions.loc[transactions["Needs Review?"].eq("Yes")]
if review.empty:
    st.success("No required transaction fields are currently missing or invalid.")
else:
    st.warning(f"{len(review):,} transaction(s) require review.")
    review_columns = [
        c
        for c in [
            "Date",
            "Transaction ID",
            "Type",
            "Category",
            "Customer / Project",
            "Amount ($)",
            "Payment Status",
            "Needs Review?",
            "Notes",
        ]
        if c in review.columns
    ]
    st.dataframe(review[review_columns], use_container_width=True, hide_index=True)

with st.expander("View filtered transaction data"):
    st.dataframe(filtered, use_container_width=True, hide_index=True)

if not ar.empty:
    with st.expander("View accounts receivable"):
        st.dataframe(ar, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Downloads")
col1, col2 = st.columns(2)
col1.download_button(
    "Download filtered transactions as CSV",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name="filtered_transactions.csv",
    mime="text/csv",
    use_container_width=True,
)
col2.download_button(
    "Download cleaned workbook",
    data=downloadable_excel(transactions, ar),
    file_name="cleaned_financial_data.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

st.caption(
    "This tool provides internal management reporting and data organization. "
    "It is not tax, audit, or professional accounting advice."
)
