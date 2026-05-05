"""Read the dossier .xlsx PDF sheet into a normalised DataFrame."""
from __future__ import annotations

import pandas as pd


def load_dossier(path) -> pd.DataFrame:
    """Load dossier xlsx PDF sheet -> normalised DataFrame."""
    df = pd.read_excel(path, sheet_name="PDF", header=4)
    df.columns = ["doc_no", "title", "rev", "status", "type_code",
                  "pdf", "volume", "book"]
    df = df[df["title"].notna() & df["type_code"].notna()
            & (df["type_code"] != "Type")].copy()
    df["doc_no"] = df["doc_no"].astype(str).str.strip()
    df["title"] = df["title"].astype(str).str.strip()
    df["type_code"] = df["type_code"].astype(str).str.strip()
    df["rev"] = df["rev"].fillna("").astype(str).str.strip()
    df["status"] = df["status"].fillna("").astype(str).str.strip()
    return df[["doc_no", "title", "rev", "status", "type_code",
               "volume"]].reset_index(drop=True)
