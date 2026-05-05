"""Read the schedule .xls into a normalised DataFrame."""
from __future__ import annotations

import pandas as pd


def load_schedule(path) -> pd.DataFrame:
    """Load schedule xls Sheet1 -> DataFrame with normalised columns."""
    df = pd.read_excel(path, sheet_name="Sheet1")
    df = df.dropna(subset=["Cust Ref #", "Title", "Discip"]).copy()
    df["cust_ref"] = df["Cust Ref #"].astype(str).str.strip()
    df = df[df["cust_ref"].str.match(r"\d{2}-\d{2}-\d{2}-\d{4}")].copy()
    df["pcs_doc_no"] = df["PCS Doc No."].astype(str).str.strip()
    df["title"] = df["Title"].astype(str).str.strip()
    df["discipline"] = df["Discip"].astype(str).str.strip()
    df["schedule_rev"] = df["Rev."].fillna("").astype(str).str.strip()
    df["seg2"] = df["cust_ref"].str.split("-").str[2]
    return df[["cust_ref", "pcs_doc_no", "title", "discipline",
               "schedule_rev", "seg2"]].reset_index(drop=True)
