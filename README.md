# Small Business Financial Dashboard MVP

A Streamlit web app that accepts the standardized financial workbook or a transaction CSV and automatically creates an interactive management dashboard.

## Features

- Upload `.xlsx`, `.xls`, or `.csv` files
- Reads the `Transactions` and optional `A_R Tracker` sheets
- Automatically calculates revenue, expenses, net cash flow, profit margin, and outstanding A/R
- Filters by date, customer/project, and category
- Interactive monthly, expense, customer, and A/R aging charts
- Data-quality review table
- Download filtered transactions and a cleaned Excel workbook

## Run locally

1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Create a virtual environment:

```bash
python -m venv .venv
```

4. Activate it:

**macOS/Linux**
```bash
source .venv/bin/activate
```

**Windows**
```powershell
.venv\Scripts\activate
```

5. Install dependencies:

```bash
pip install -r requirements.txt
```

6. Start the app:

```bash
streamlit run app.py
```

The terminal will show a local address, usually `http://localhost:8501`.

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload `app.py`, `requirements.txt`, and optionally the sample workbook.
3. Sign in to Streamlit Community Cloud with GitHub.
4. Select **Create app**.
5. Choose the repository, branch, and `app.py` as the entrypoint.
6. Deploy.

## Expected workbook structure

### `Transactions` sheet

The app expects the actual headers on the second row, matching the supplied template. Required columns:

- Date
- Type
- Category
- Customer / Project
- Amount ($)
- Payment Status

### `A_R Tracker` sheet

Optional but recommended. Relevant columns include:

- Invoice #
- Customer
- Invoice Date
- Due Date
- Original Amount ($)
- Amount Paid ($)
- Balance Due ($)
- Status
- Days Outstanding

## Important privacy note

The current MVP processes uploaded data during the active Streamlit session. Before using real client financial information publicly, add authentication, a privacy policy, controlled data retention, and appropriate security practices. Begin by using the app privately yourself rather than giving public access to clients.
