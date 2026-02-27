"""
Cross GT question/answer generator.

Refactors the notebook-style logic into callable functions:
- preprocess_usage_forecast(): normalization & derived columns
- apply_resource_filter(): resource-prefix filtering (moved into preprocessing area)
- generate_cross_gt(): generates cross GT question/answer pairs, supports variants, saves CSV

Expected inputs:
- usage_df_raw: original usage dataframe
- forecast_df_raw: original forecast dataframe
- resource_prefix: "COMPUTE", "SQLVMPT", or ""
- output_csv_path: output location for CSV
- verbose: print Q/A pairs if True
- n_variants: number of similar variants to generate for templates that use random_region/crg/cpu/customer
"""

from __future__ import annotations

import datetime as dt
import random
import calendar
from dataclasses import dataclass
from typing import Callable, Optional, Any

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta


OUT_OF_SCOPE_ANSWER = "I cannot answer this question since it's outside of the scope of the data."


# -----------------------------
# Preprocessing (from preprocess notebook)
# -----------------------------

RESOURCE_MAP = {
    "COMPUTE": "COMPUTE:CORES",
    "SQLVMPT": "SQLVM PASSTHROUGH:CORES",
    "": "",  # empty means no resource filter
}

ALLOWED_RESOURCE_TYPES = ["COMPUTE:CORES", "SQLVM PASSTHROUGH:CORES"]


def preprocess_usage_forecast(
    usage_df_raw: pd.DataFrame,
    forecast_df_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Normalize raw usage & forecast dataframes so downstream GT templates are stable.
    """
    usage_df = usage_df_raw.copy()
    forecast_df = forecast_df_raw.copy()

    # ---- Usage ----
    if "ResourceType" in usage_df.columns:
        usage_df = usage_df[usage_df["ResourceType"].isin(ALLOWED_RESOURCE_TYPES)]

    if "Date" in usage_df.columns:
        usage_df["Date"] = pd.to_datetime(usage_df["Date"], errors="coerce")

    if "CPUSupplierName" in usage_df.columns and "CPUSupplier" not in usage_df.columns:
        usage_df = usage_df.rename(columns={"CPUSupplierName": "CPUSupplier"})

    # Keep legacy compatibility with your notebook
    if "SegmentCustomer" in usage_df.columns and "Customer" not in usage_df.columns:
        usage_df["Customer"] = usage_df["SegmentCustomer"]

    if "Geo" in usage_df.columns:
        usage_df = usage_df.drop(columns=["Geo"])

    # ---- Forecast ----
    if "ResourceType" in forecast_df.columns:
        forecast_df = forecast_df[forecast_df["ResourceType"].isin(ALLOWED_RESOURCE_TYPES)]

    if "ForecastMonth" in forecast_df.columns:
        forecast_df["ForecastMonth"] = pd.to_datetime(forecast_df["ForecastMonth"], errors="coerce")

    rename_map = {}
    if "CPUSupplierName" in forecast_df.columns and "CPUSupplier" not in forecast_df.columns:
        rename_map["CPUSupplierName"] = "CPUSupplier"
    if "OrganicForecast" in forecast_df.columns and "Organic Forecast" not in forecast_df.columns:
        rename_map["OrganicForecast"] = "Organic Forecast"
    if "InorganicForecast" in forecast_df.columns and "Inorganic Forecast" not in forecast_df.columns:
        rename_map["InorganicForecast"] = "Inorganic Forecast"
    if rename_map:
        forecast_df = forecast_df.rename(columns=rename_map)

    # POR parsing from PublicationMonth (e.g., "January 2026 POR" -> "January 2026")
    if "PublicationMonth" in forecast_df.columns and "POR" not in forecast_df.columns:
        forecast_df["POR"] = forecast_df["PublicationMonth"].astype(str).str[:-4]
        forecast_df["POR"] = pd.to_datetime(forecast_df["POR"], errors="coerce")

    if "Forecast" in forecast_df.columns:
        forecast_df["Forecast"] = pd.to_numeric(forecast_df["Forecast"], errors="coerce")

    # horizon/lag
    if all(col in forecast_df.columns for col in ["ForecastMonth", "POR"]):
        forecast_df["horizon"] = (
            (forecast_df["ForecastMonth"].dt.year - forecast_df["POR"].dt.year) * 12
            + (forecast_df["ForecastMonth"].dt.month - forecast_df["POR"].dt.month)
            + 1
        )
        forecast_df["lag"] = forecast_df["horizon"]

    if "Geo" in forecast_df.columns:
        forecast_df = forecast_df.drop(columns=["Geo"])

    return usage_df, forecast_df


def apply_resource_filter(
    usage_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    resource_prefix: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Apply resource filtering based on prefix input: "COMPUTE", "SQLVMPT", or "".
    """
    resource_prefix = (resource_prefix or "").strip().upper()
    # Normalize accepted inputs (e.g., allow "compute" too)
    if resource_prefix not in RESOURCE_MAP:
        raise ValueError(f"resource_prefix must be one of {list(RESOURCE_MAP.keys())}, got: {resource_prefix}")

    res_val = RESOURCE_MAP[resource_prefix]
    if not res_val:
        return usage_df, forecast_df

    if "ResourceType" not in usage_df.columns or "ResourceType" not in forecast_df.columns:
        # If columns not present, return as-is (or raise; but safer for now)
        return usage_df, forecast_df

    return (
        usage_df[usage_df["ResourceType"] == res_val],
        forecast_df[forecast_df["ResourceType"] == res_val],
    )


# -----------------------------
# Cross GT generation
# -----------------------------

@dataclass(frozen=True)
class CrossContext:
    run_date: str
    latest_por: str
    last_por: str
    earliest_por: str
    early_por: str

    available_por_dt_ordered: list[pd.Timestamp]
    latest_actual_month_dt: pd.Timestamp
    latest_actual_month_str: str

    target_month_dt: pd.Timestamp
    target_month_str: str

    # Pools for variants (top-5 in latest POR)
    top_regions: list[str]
    top_crgs: list[str]
    top_customers: list[str]
    top_cpus: list[str]


@dataclass(frozen=True)
class Variant:
    random_region: Optional[str] = None
    random_crg: Optional[str] = None
    random_seg_cus: Optional[str] = None
    random_cpu: Optional[str] = None


TemplateFn = Callable[[pd.DataFrame, pd.DataFrame, CrossContext, Variant, str], tuple[str, str]]


@dataclass(frozen=True)
class Template:
    """
    A GT template that can render question+answer.
    variantable: whether to generate n_variants versions (else just 1)
    """
    name: str
    fn: TemplateFn
    variantable: bool


def build_cross_context(
    df_usage_resource: pd.DataFrame,
    df_fcst_resource: pd.DataFrame,
    *,
    now: Optional[dt.datetime] = None,
    top_n: int = 5,
) -> CrossContext:
    if now is None:
        now = dt.datetime.now()

    run_date = now.strftime("%Y-%m-%d %H:%M:%S")

    # POR orderings from FILTERED forecast df
    por_df = df_fcst_resource[["PublicationMonth", "POR"]].dropna().drop_duplicates().sort_values("POR")
    available_por_str_ordered = por_df["PublicationMonth"].unique().tolist()
    available_por_dt_ordered = sorted(df_fcst_resource["POR"].dropna().unique())

    if len(available_por_str_ordered) < 2 or len(available_por_dt_ordered) < 2:
        raise ValueError("Not enough POR history in filtered forecast dataframe to build context.")

    earliest_por = available_por_str_ordered[0]
    latest_por = available_por_str_ordered[-1]
    last_por = available_por_str_ordered[-2]

    # pick an early POR not first/last/latest
    if len(available_por_str_ordered) > 3:
        early_idx = random.randint(1, len(available_por_str_ordered) - 3)
        early_por = available_por_str_ordered[early_idx]
    else:
        early_por = earliest_por

    # Latest actual month = month before latest POR date
    latest_por_dt = pd.Timestamp(available_por_dt_ordered[-1])
    latest_actual_month_dt = latest_por_dt - relativedelta(months=1)
    latest_actual_month_str = pd.Timestamp(latest_actual_month_dt).strftime("%B %Y")

    # Target month randomization based on "now"
    current_month = now.month
    all_months = [current_month - i for i in range(1, 4)]
    all_months = [(m if m > 0 else m + 12) for m in all_months]
    random_month = random.choice(all_months)
    random_month_year = now.year if random_month < current_month else now.year - 1
    target_month_dt = pd.Timestamp(year=random_month_year, month=random_month, day=1)
    target_month_str = target_month_dt.strftime("%B %Y")

    # Pools from latest POR slice (FILTERED)
    df_fcst_latest_por = df_fcst_resource[df_fcst_resource["PublicationMonth"] == latest_por].copy()

    def top_values(col: str) -> list[str]:
        if col not in df_fcst_latest_por.columns or "Forecast" not in df_fcst_latest_por.columns:
            return []
        s = (
            df_fcst_latest_por.dropna(subset=[col, "Forecast"])
            .groupby(col)["Forecast"].sum()
            .sort_values(ascending=False)
            .head(top_n)
        )
        return [str(x) for x in s.index.tolist()]

    top_regions = top_values("Region")
    top_crgs = top_values("CRG")
    top_customers = top_values("SegmentCustomer")
    top_cpus = top_values("CPUSupplier")

    return CrossContext(
        run_date=run_date,
        latest_por=latest_por,
        last_por=last_por,
        earliest_por=earliest_por,
        early_por=early_por,
        available_por_dt_ordered=[pd.Timestamp(x) for x in available_por_dt_ordered],
        latest_actual_month_dt=pd.Timestamp(latest_actual_month_dt),
        latest_actual_month_str=latest_actual_month_str,
        target_month_dt=target_month_dt,
        target_month_str=target_month_str,
        top_regions=top_regions,
        top_crgs=top_crgs,
        top_customers=top_customers,
        top_cpus=top_cpus,
    )


def make_variants(ctx: CrossContext, n_variants: int) -> list[Variant]:
    """
    Create up to n_variants variants using pools from context.
    Ensures different values where possible by sampling without replacement.
    """
    n_variants = max(1, int(n_variants or 1))

    def sample_pool(pool: list[str]) -> list[Optional[str]]:
        if not pool:
            return [None] * n_variants
        k = min(n_variants, len(pool))
        picked = random.sample(pool, k=k)
        # If user asks more variants than pool size, repeat cyclically
        if k < n_variants:
            picked = (picked * ((n_variants // k) + 1))[:n_variants]
        return picked

    regions = sample_pool(ctx.top_regions)
    crgs = sample_pool(ctx.top_crgs)
    customers = sample_pool(ctx.top_customers)
    cpus = sample_pool(ctx.top_cpus)

    return [
        Variant(
            random_region=regions[i],
            random_crg=crgs[i],
            random_seg_cus=customers[i],
            random_cpu=cpus[i],
        )
        for i in range(n_variants)
    ]


# -----------------------------
# Template implementations (12 questions)
# -----------------------------
# Note: resource_prefix_label is only for question string prefix (e.g., "COMPUTE ").
# You asked to accept "COMPUTE" as input; we can label it as "COMPUTE " in question.
def _resource_label(resource_prefix: str) -> str:
    rp = (resource_prefix or "").strip().upper()
    if rp == "COMPUTE":
        return "COMPUTE "
    if rp == "SQLVMPT":
        return "SQLVMPT "
    return ""


def tmpl_cross_q01(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    question = (
        f"{_resource_label(resource_prefix)}Compare total usage and total forecasts, what is the MAPE for each month "
        f"respectively considering lag 3 forecasts on worldwide level? Report results for each month respectively."
    )
    try:
        df_usage_filtered = u.dropna(subset=["Usage"])
        df_fcst_filtered = f[(f["lag"] == 3)].dropna(subset=["Forecast"])

        df_fcst_agg = df_fcst_filtered.groupby("ForecastMonth")["Forecast"].sum().reset_index()
        df_usage_agg = df_usage_filtered.groupby("Date")["Usage"].sum().reset_index()

        merged = pd.merge(df_usage_agg, df_fcst_agg, left_on="Date", right_on="ForecastMonth", how="inner")
        if merged.empty:
            answer = "Not enough overlapping months to compute MAPE."
        else:
            merged["MAPE"] = (merged["Usage"] - merged["Forecast"]).abs() / merged["Usage"] * 100
            answer = " | ".join(f"{row['Date'].strftime('%b %Y')}: {row['MAPE']:.2f}%" for _, row in merged.iterrows())
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q02(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    question = (
        f"{_resource_label(resource_prefix)}Compare total usage and total forecasts, what is the MAPE for each month "
        f"respectively considering lag 6 forecasts on worldwide level? Report results for each month respectively."
    )
    try:
        df_usage_filtered = u.dropna(subset=["Usage"])
        df_fcst_filtered = f[(f["lag"] == 6)].dropna(subset=["Forecast"])

        df_fcst_agg = df_fcst_filtered.groupby("ForecastMonth")["Forecast"].sum().reset_index()
        df_usage_agg = df_usage_filtered.groupby("Date")["Usage"].sum().reset_index()

        merged = pd.merge(df_usage_agg, df_fcst_agg, left_on="Date", right_on="ForecastMonth", how="inner")
        if merged.empty:
            answer = "Not enough overlapping months to compute MAPE."
        else:
            merged["MAPE"] = (merged["Usage"] - merged["Forecast"]).abs() / merged["Usage"] * 100
            answer = " | ".join(f"{row['Date'].strftime('%b %Y')}: {row['MAPE']:.2f}%" for _, row in merged.iterrows())
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q03(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    crg = v.random_crg
    question = (
        f"{_resource_label(resource_prefix)}Compare total usage and total forecasts, what is the MAPE for each month "
        f"respectively considering lag 3 forecasts for the CRG {crg}? Report results for each month respectively."
    )
    if not crg:
        return question, "Not enough data to answer this question."
    try:
        df_usage = u[(u["CRG"] == crg) & (u["Usage"].notnull())].groupby("Date")["Usage"].sum().reset_index()
        df_fcst = (
            f[(f["CRG"] == crg) & (f["lag"] == 3) & (f["Forecast"].notnull())]
            .groupby("ForecastMonth")["Forecast"]
            .sum()
            .reset_index()
        )

        merged = pd.merge(df_usage, df_fcst, left_on="Date", right_on="ForecastMonth", how="inner")
        if merged.empty:
            answer = "Not enough overlapping months to compute MAPE."
        else:
            merged["MAPE"] = (merged["Usage"] - merged["Forecast"]).abs() / merged["Usage"] * 100
            answer = " | ".join(f"{row['Date'].strftime('%b %Y')}: {row['MAPE']:.2f}%" for _, row in merged.iterrows())
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q04(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    cpu = v.random_cpu
    region = v.random_region
    question = (
        f"{_resource_label(resource_prefix)}Compare total usage and total forecasts, what is the MAPE for each month "
        f"respectively considering lag 3 forecasts for the CPU Supplier {cpu} in {region}? "
        f"Report results for each month respectively."
    )
    if not cpu or not region:
        return question, "Not enough data to answer this question."
    try:
        df_usage_filtered = u[(u["CPUSupplier"] == cpu) & (u["Region"] == region) & (u["Usage"].notnull())]
        df_fcst_filtered = f[
            (f["CPUSupplier"] == cpu)
            & (f["Region"] == region)
            & (f["lag"] == 3)
            & (f["Forecast"].notnull())
        ]
        df_fcst_agg = df_fcst_filtered.groupby("ForecastMonth")["Forecast"].sum().reset_index()
        df_usage_agg = df_usage_filtered.groupby("Date")["Usage"].sum().reset_index()
        merged = pd.merge(df_usage_agg, df_fcst_agg, left_on="Date", right_on="ForecastMonth", how="inner")

        if merged.empty:
            answer = "Not enough overlapping months to compute MAPE."
        else:
            merged["MAPE"] = (merged["Usage"] - merged["Forecast"]).abs() / merged["Usage"] * 100
            answer = " | ".join(f"{row['Date'].strftime('%b %Y')}: {row['MAPE']:.2f}%" for _, row in merged.iterrows())
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q05(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    # This uses region + "first future forecast". We'll interpret first future forecast month as latest POR month.
    region = v.random_region
    first_future_fcst_month_dt = pd.Timestamp(ctx.available_por_dt_ordered[-1])
    first_future_fcst_month_str = first_future_fcst_month_dt.strftime("%B %Y")

    question = (
        f"{_resource_label(resource_prefix)}What is the gap between the latest actuals and the first future forecasts "
        f"for {region} in the {ctx.latest_por}?"
    )
    if not region:
        return question, "Not enough data to answer this question."
    try:
        usage_actual = u[(u["Region"] == region) & (u["Date"] == ctx.latest_actual_month_dt)]["Usage"].sum()
        forecast_value = f[
            (f["Region"] == region)
            & (f["ForecastMonth"] == first_future_fcst_month_dt)
            & (f["PublicationMonth"] == ctx.latest_por)
        ]["Forecast"].sum()

        gap = forecast_value - usage_actual
        answer = (
            f"The gap between the latest actuals ({ctx.latest_actual_month_str}) and the first future forecast "
            f"({first_future_fcst_month_str}) for {region} in the {ctx.latest_por} POR is {gap}."
        )
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q06(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    crg = v.random_crg
    first_future_fcst_month_dt = pd.Timestamp(ctx.available_por_dt_ordered[-1])
    first_future_fcst_month_str = first_future_fcst_month_dt.strftime("%B %Y")

    question = (
        f"{_resource_label(resource_prefix)}What is the gap between the {ctx.latest_actual_month_str} actuals and the "
        f"{first_future_fcst_month_str} forecasts for the CRG {crg} in the {ctx.latest_por}?"
    )
    if not crg:
        return question, "Not enough data to answer this question."
    try:
        usage_actual = u[(u["CRG"] == crg) & (u["Date"] == ctx.latest_actual_month_dt)]["Usage"].sum()
        forecast_value = f[
            (f["CRG"] == crg)
            & (f["ForecastMonth"] == first_future_fcst_month_dt)
            & (f["PublicationMonth"] == ctx.latest_por)
        ]["Forecast"].sum()

        gap = forecast_value - usage_actual
        answer = (
            f"The gap between the latest actuals ({ctx.latest_actual_month_str}) and the first future forecast "
            f"({first_future_fcst_month_str}) for the CRG {crg} in the {ctx.latest_por} POR is {gap}."
        )
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q07(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    question = (
        f"{_resource_label(resource_prefix)}List the top five regions that contribute to the error for "
        f"{ctx.target_month_str}, considering the lag-3 forecast."
    )
    try:
        df_usage_filtered = u[
            (u["Date"] == ctx.target_month_dt)
            & (u["Usage"].notnull())
            & (u["Region"].notnull())
        ]
        df_fcst_filtered = f[
            (f["ForecastMonth"] == ctx.target_month_dt)
            & (f["lag"] == 3)
            & (f["Forecast"].notnull())
            & (f["Region"].notnull())
        ]

        df_usage_grouped = df_usage_filtered.groupby(["Region", "Date"])["Usage"].sum().reset_index()
        df_fcst_grouped = df_fcst_filtered.groupby(["Region", "ForecastMonth"])["Forecast"].sum().reset_index()

        merged = pd.merge(
            df_usage_grouped,
            df_fcst_grouped,
            left_on=["Region", "Date"],
            right_on=["Region", "ForecastMonth"],
            how="inner",
        )

        error_series = (
            merged.groupby("Region")
            .apply(lambda x: (x["Usage"] - x["Forecast"]).abs().sum())
            .sort_values(ascending=False)
            .head(5)
        )

        if error_series.empty:
            answer = "There is no data to answer your question."
        else:
            answer = " | ".join(error_series.index.tolist())
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q08(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    question = (
        f"{_resource_label(resource_prefix)}Show the top 5 regions with highest absolute error since "
        f"{ctx.target_month_str}, considering lag 3 forecasts"
    )
    try:
        df_usage_f = (
            u[(u["Usage"].notnull()) & (u["Region"].notnull())]
            .groupby(["Region", "Date"])["Usage"]
            .sum()
            .reset_index()
        )
        df_fcst_f = (
            f[(f["lag"] == 3) & (f["Forecast"].notnull()) & (f["Region"].notnull())]
            .groupby(["Region", "ForecastMonth"])["Forecast"]
            .sum()
            .reset_index()
        )

        merged = pd.merge(
            df_usage_f,
            df_fcst_f,
            left_on=["Region", "Date"],
            right_on=["Region", "ForecastMonth"],
            how="inner",
        )
        merged = merged[merged["Date"] >= ctx.target_month_dt]

        if merged.empty:
            return question, "There is no data to answer your question."

        merged["abs_error"] = (merged["Usage"] - merged["Forecast"]).abs()
        region_error = merged.groupby("Region")["abs_error"].sum().sort_values(ascending=False).head(5)

        if region_error.empty:
            answer = "There is no data to answer your question."
        else:
            answer = (
                f"Top 5 regions with highest absolute error since {ctx.target_month_str}, "
                f"considering lag 3 forecasts: {region_error.index.tolist()}."
            )
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q09(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    question = (
        f"{_resource_label(resource_prefix)}List the top five SegmentCustomers that contribute to the error for "
        f"{ctx.target_month_str}, considering the lag-3 forecast."
    )
    try:
        usage_grp = (
            u[(u["Date"] == ctx.target_month_dt) & (u["Usage"].notnull()) & (u["SegmentCustomer"].notnull())]
            .groupby("SegmentCustomer")["Usage"]
            .sum()
            .reset_index()
        )
        fcst_grp = (
            f[
                (f["ForecastMonth"] == ctx.target_month_dt)
                & (f["lag"] == 3)
                & (f["Forecast"].notnull())
                & (f["SegmentCustomer"].notnull())
            ]
            .groupby("SegmentCustomer")["Forecast"]
            .sum()
            .reset_index()
        )

        merged = pd.merge(usage_grp, fcst_grp, on="SegmentCustomer", how="inner")
        merged["AbsError"] = (merged["Forecast"] - merged["Usage"]).abs()

        top5 = merged.sort_values("AbsError", ascending=False).head(5)
        if top5.empty:
            answer = "There is no data to answer your question."
        else:
            customers = top5["SegmentCustomer"].tolist()
            answer = (
                f"For {ctx.target_month_str}, considering the lag-3 forecast, the top five SegmentCustomers "
                f"contributing to the error are {', '.join(customers)}."
            )
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q10(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    question = (
        f"{_resource_label(resource_prefix)}Show the top 5 Segment Customers with highest absolute error since "
        f"{ctx.target_month_str} considering lag 3 forecasts."
    )
    try:
        u_f = (
            u[u["Date"] >= ctx.target_month_dt]
            .dropna(subset=["SegmentCustomer", "Usage"])
            .groupby(["Date", "SegmentCustomer"])["Usage"]
            .sum()
            .reset_index()
        )
        f_f = (
            f[(f["ForecastMonth"] >= ctx.target_month_dt) & (f["lag"] == 3)]
            .dropna(subset=["SegmentCustomer", "Forecast"])
            .groupby(["ForecastMonth", "SegmentCustomer"])["Forecast"]
            .sum()
            .reset_index()
        )

        merged = pd.merge(
            u_f,
            f_f,
            left_on=["Date", "SegmentCustomer"],
            right_on=["ForecastMonth", "SegmentCustomer"],
            how="inner",
        )

        if merged.empty:
            return question, "There is no data to answer your question."

        merged["abs_error"] = (merged["Usage"] - merged["Forecast"]).abs()
        err = merged.groupby("SegmentCustomer")["abs_error"].sum().sort_values(ascending=False).head(5)

        if err.empty:
            answer = "There is no data to answer your question."
        else:
            answer = (
                f"Considering the lag 3 forecast, the top 5 Segment Customers contributing to the error since "
                f"{ctx.target_month_str} are: {err.index.tolist()}."
            )
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q11(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    # Uses random customer
    customer = v.random_seg_cus
    # Pick a FY-end (June) forecast month in latest POR; if none, out-of-scope-ish
    df_latest = f[f["PublicationMonth"] == ctx.latest_por]
    june_months = df_latest[df_latest["ForecastMonth"].dt.month == 6]["ForecastMonth"].dropna().unique()
    fy_month = pd.Timestamp(random.choice(june_months)) if len(june_months) else None
    fy_year = fy_month.year if fy_month is not None else None

    question = (
        f"{_resource_label(resource_prefix)}What is the incremental forecast for FY{fy_year} for the Customer "
        f"{customer} considering the {ctx.latest_por}?"
    )
    if not customer or fy_month is None or fy_year is None:
        return question, "Not enough data to answer this question."

    try:
        fc = f[(f["SegmentCustomer"] == customer) & (f["PublicationMonth"] == ctx.latest_por)]
        forecast_agg = fc[fc["ForecastMonth"] == fy_month]["Forecast"].sum()

        prev_fy_dt = pd.Timestamp(f"{fy_year - 1}-06-01")
        if prev_fy_dt in fc["ForecastMonth"].values:
            prev_year_agg = fc[fc["ForecastMonth"] == prev_fy_dt]["Forecast"].sum()
        elif "Date" in u.columns and prev_fy_dt in u["Date"].values:
            prev_year_agg = u[(u["SegmentCustomer"] == customer) & (u["Date"] == prev_fy_dt)]["Usage"].sum()
        else:
            return question, "Not enough data to answer this question."

        incremental_forecast = forecast_agg - prev_year_agg
        answer = (
            f"Incremental forecast for FY{fy_year} for the Customer {customer} considering {ctx.latest_por}: "
            f"{incremental_forecast:.2f}"
        )
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


def tmpl_cross_q12(u: pd.DataFrame, f: pd.DataFrame, ctx: CrossContext, v: Variant, resource_prefix: str):
    crg = v.random_crg
    df_latest = f[f["PublicationMonth"] == ctx.latest_por]
    june_months = df_latest[df_latest["ForecastMonth"].dt.month == 6]["ForecastMonth"].dropna().unique()
    fy_month = pd.Timestamp(random.choice(june_months)) if len(june_months) else None
    fy_year = fy_month.year if fy_month is not None else None

    question = (
        f"{_resource_label(resource_prefix)}What is the incremental forecast of fiscal year{fy_year} of CRG {crg} "
        f"considering the {ctx.latest_por}?"
    )
    if not crg or fy_month is None or fy_year is None:
        return question, "Not enough data to answer this question."

    try:
        fc = f[(f["PublicationMonth"] == ctx.latest_por) & (f["CRG"] == crg)]
        forecast_agg = fc[fc["ForecastMonth"] == fy_month]["Forecast"].sum()

        prev_fy_dt = pd.Timestamp(f"{fy_year - 1}-06-01")
        if prev_fy_dt in fc["ForecastMonth"].values:
            prev_year_agg = fc[fc["ForecastMonth"] == prev_fy_dt]["Forecast"].sum()
        elif "Date" in u.columns and prev_fy_dt in u["Date"].values:
            prev_year_agg = u[(u["CRG"] == crg) & (u["Date"] == prev_fy_dt)]["Usage"].sum()
        else:
            return question, "Not enough data to answer this question."

        incremental_forecast = forecast_agg - prev_year_agg
        answer = (
            f"Incremental forecast for FY{fy_year} of CRG {crg} considering the {ctx.latest_por} POR: "
            f"{incremental_forecast:.2f}"
        )
    except Exception:
        answer = "An error occurred. Couldn't answer the question."
    return question, answer


TEMPLATES: list[Template] = [
    Template(name="cross_q01", fn=tmpl_cross_q01, variantable=False),
    Template(name="cross_q02", fn=tmpl_cross_q02, variantable=False),
    Template(name="cross_q03", fn=tmpl_cross_q03, variantable=True),
    Template(name="cross_q04", fn=tmpl_cross_q04, variantable=True),
    Template(name="cross_q05", fn=tmpl_cross_q05, variantable=True),
    Template(name="cross_q06", fn=tmpl_cross_q06, variantable=True),
    Template(name="cross_q07", fn=tmpl_cross_q07, variantable=False),
    Template(name="cross_q08", fn=tmpl_cross_q08, variantable=False),
    Template(name="cross_q09", fn=tmpl_cross_q09, variantable=False),
    Template(name="cross_q10", fn=tmpl_cross_q10, variantable=False),
    Template(name="cross_q11", fn=tmpl_cross_q11, variantable=True),
    Template(name="cross_q12", fn=tmpl_cross_q12, variantable=True),
]


def generate_cross_gt(
    usage_df_raw: pd.DataFrame,
    forecast_df_raw: pd.DataFrame,
    *,
    resource_prefix: str,
    output_csv_path: str,
    verbose: bool = False,
    n_variants: int = 1,
    out_of_scope_templates: Optional[set[str]] = None,
) -> pd.DataFrame:
    """
    Main entrypoint: generates cross GT output dataframe and saves to CSV.
    """
    out_of_scope_templates = out_of_scope_templates or set()

    usage_norm, fcst_norm = preprocess_usage_forecast(usage_df_raw, forecast_df_raw)
    df_usage_resource, df_fcst_resource = apply_resource_filter(usage_norm, fcst_norm, resource_prefix)

    # Build context based on FILTERED DFs
    ctx = build_cross_context(df_usage_resource, df_fcst_resource)

    rows: list[dict[str, Any]] = []
    q_counter = 1

    for tmpl in TEMPLATES:
        # Decide how many variants for this template
        n = int(n_variants) if tmpl.variantable else 1
        variants = make_variants(ctx, n) if tmpl.variantable else [Variant()]

        for v in variants:
            question_id = f"cross_q{q_counter:03d}"
            q_counter += 1

            if tmpl.name in out_of_scope_templates:
                question, _ = tmpl.fn(df_usage_resource, df_fcst_resource, ctx, v, resource_prefix)
                answer = OUT_OF_SCOPE_ANSWER
            else:
                question, answer = tmpl.fn(df_usage_resource, df_fcst_resource, ctx, v, resource_prefix)

            if verbose:
                print(question_id)
                print(question)
                print(answer)
                print("-" * 80)

            rows.append(
                {
                    "run_date": ctx.run_date,
                    "question_id": question_id,
                    "question": question,
                    "ground_truth": answer,
                }
            )

    out_df = pd.DataFrame(rows)
    out_df.to_csv(output_csv_path, index=False)
    return out_df