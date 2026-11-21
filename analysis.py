#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Quantitative analysis for the student delay-discounting questionnaire.

The input workbook is expected to have 26 columns:
  A = timestamp
  B:Z = questionnaire questions 1:25

The analysis deliberately treats Q4-Q12 and Q13-Q21 as two different
contexts:
  * Q4-Q12: immediate monetary choices; used to estimate a Kirby-like k.
  * Q13-Q21: the matched choices shifted one year into the future; used to
    study context effects / preference reversals, not to estimate a second
    standard k.

This script produces aggregate summaries, participant-level derived metrics,
item-level summaries, preference-reversal counts, and figures.

Usage examples:
    python analysis.py --input data/stub_responses.xlsx --output outputs/stub
    python analysis.py --input data/private/raw_responses_private.xlsx --output outputs/private
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# Questionnaire specification
# ---------------------------------------------------------------------------

# Q4-Q12: 10 EUR today vs larger amount after D days.
# Q13-Q21: same extra delays, but both alternatives shifted +1 year.
MONETARY_ITEMS = [
    {"q_now": 4,  "q_future": 13, "small": 10.0, "large": 11.0,  "delay_days": 1},
    {"q_now": 5,  "q_future": 14, "small": 10.0, "large": 12.0,  "delay_days": 3},
    {"q_now": 6,  "q_future": 15, "small": 10.0, "large": 15.0,  "delay_days": 7},
    {"q_now": 7,  "q_future": 16, "small": 10.0, "large": 18.0,  "delay_days": 14},
    {"q_now": 8,  "q_future": 17, "small": 10.0, "large": 20.0,  "delay_days": 30},
    {"q_now": 9,  "q_future": 18, "small": 10.0, "large": 25.0,  "delay_days": 90},
    {"q_now": 10, "q_future": 19, "small": 10.0, "large": 35.0,  "delay_days": 180},
    {"q_now": 11, "q_future": 20, "small": 10.0, "large": 60.0,  "delay_days": 365},
    {"q_now": 12, "q_future": 21, "small": 10.0, "large": 100.0, "delay_days": 730},
]

for item in MONETARY_ITEMS:
    # Indifference threshold for the immediate-context item:
    # S = L / (1 + kD)  =>  k = (L/S - 1)/D
    item["k_threshold"] = (
        item["large"] / item["small"] - 1.0
    ) / item["delay_days"]

LIKERT_MAP = {
    "Διαφωνώ απόλυτα": 1,
    "Μάλλον διαφωνώ": 2,
    "Ούτε διαφωνώ / Ούτε συμφωνώ": 3,
    "Μάλλον συμφωνώ": 4,
    "Συμφωνώ απόλυτα": 5,
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _text(value) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).split()).strip()


def parse_now_choice(value):
    """Return 0=SIR, 1=LDR for Q4-Q12; NaN if missing/unrecognized."""
    s = _text(value)
    if not s:
        return np.nan
    if "10€ σήμερα" in s or "10 € σήμερα" in s:
        return 0
    if "€" in s:
        return 1
    return np.nan


def parse_future_choice(value):
    """Return 0=SIR, 1=LDR for Q13-Q21; NaN if missing/unrecognized."""
    s = _text(value)
    if not s:
        return np.nan
    if "10€ σε 1 χρόνο ακριβώς" in s or "10 € σε 1 χρόνο ακριβώς" in s:
        return 0
    if "€" in s:
        return 1
    return np.nan


def parse_school_choice(value):
    """Return 1=study today, 0=play/relax today; NaN if missing."""
    s = _text(value).lower()
    if not s:
        return np.nan
    if "να διαβάσω" in s:
        return 1
    if "να παίξω" in s or "χαλαρώσω" in s:
        return 0
    return np.nan


def parse_likert(value):
    return LIKERT_MAP.get(_text(value), np.nan)


# ---------------------------------------------------------------------------
# Kirby-like k scoring for the custom 9-item immediate block
# ---------------------------------------------------------------------------

def geometric_mean(values: Iterable[float]) -> float:
    values = np.asarray(list(values), dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if len(values) == 0:
        return np.nan
    return float(np.exp(np.mean(np.log(values))))


def kirby_like_score(row: pd.Series, min_answered: int = 7) -> dict:
    """Estimate a best-fitting k from Q4-Q12 by maximum consistency.

    The nine immediate-context items are sorted by their indifference k.
    For each possible switching region we calculate the fraction of observed
    answers consistent with that region. We select the region(s) with maximum
    consistency. If several regions tie, the reported k is the geometric mean
    of their representative k values.

    A response is labelled ``reliable`` when at least ``min_answered`` monetary
    items are present and maximum consistency is >= 75%. With 9 complete items,
    this means at least 7/9 choices are consistent with the best-fitting region.
    """
    observed = []
    for item in MONETARY_ITEMS:
        c = parse_now_choice(row.iloc[item["q_now"]])
        if pd.notna(c):
            observed.append((item["k_threshold"], int(c)))

    observed.sort(key=lambda x: x[0])
    n = len(observed)
    if n == 0:
        return {
            "k": np.nan,
            "ln_k": np.nan,
            "consistency": np.nan,
            "n_answered": 0,
            "n_best_regions": 0,
            "reliable": False,
        }

    thresholds = np.asarray([x[0] for x in observed], dtype=float)
    choices = np.asarray([x[1] for x in observed], dtype=int)

    candidates = []
    # For thresholds sorted low->high, a single stable k predicts a monotone
    # pattern 0...0,1...1 (SIR first, LDR later) across possible switch points.
    for r in range(n + 1):
        expected = np.asarray([0] * r + [1] * (n - r), dtype=int)
        consistency = float(np.mean(expected == choices))

        if r == 0:
            representative_k = thresholds[0]
        elif r == n:
            representative_k = thresholds[-1]
        else:
            representative_k = math.sqrt(thresholds[r - 1] * thresholds[r])

        candidates.append((consistency, representative_k))

    best_consistency = max(x[0] for x in candidates)
    best_ks = [
        x[1] for x in candidates
        if math.isclose(x[0], best_consistency, abs_tol=1e-12)
    ]
    k_hat = geometric_mean(best_ks)

    return {
        "k": k_hat,
        "ln_k": math.log(k_hat) if np.isfinite(k_hat) and k_hat > 0 else np.nan,
        "consistency": best_consistency,
        "n_answered": n,
        "n_best_regions": len(best_ks),
        "reliable": bool(n >= min_answered and best_consistency >= 0.75),
    }


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def welch_df(a: np.ndarray, b: np.ndarray) -> float:
    """Welch-Satterthwaite degrees of freedom."""
    n1, n2 = len(a), len(b)
    v1, v2 = np.var(a, ddof=1), np.var(b, ddof=1)
    numerator = (v1 / n1 + v2 / n2) ** 2
    denominator = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    return float(numerator / denominator)


def cochrans_q(binary_matrix: np.ndarray) -> tuple[float, int, float]:
    """Cochran's Q for k related binary measurements.

    binary_matrix: n participants x k repeated binary conditions.
    """
    x = np.asarray(binary_matrix, dtype=float)
    if x.ndim != 2:
        raise ValueError("Cochran's Q expects a 2D matrix")
    k = x.shape[1]
    col_sums = x.sum(axis=0)
    row_sums = x.sum(axis=1)
    total = col_sums.sum()
    denominator = k * total - np.sum(row_sums ** 2)
    if denominator == 0:
        return np.nan, k - 1, np.nan
    q = (k - 1) * (k * np.sum(col_sums ** 2) - total ** 2) / denominator
    p = float(stats.chi2.sf(q, k - 1))
    return float(q), k - 1, p


def fmt_p(p: float) -> str:
    if not np.isfinite(p):
        return "NA"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run_analysis(input_path: Path, output_dir: Path, min_answered: int = 7) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(input_path, sheet_name=0, engine="openpyxl")
    if df.shape[1] < 26:
        raise ValueError(
            f"Expected at least 26 columns (timestamp + Q1-Q25); found {df.shape[1]}."
        )

    participant_rows = []
    reversal_rows = []

    for idx, row in df.iterrows():
        score = kirby_like_score(row, min_answered=min_answered)

        now = [parse_now_choice(row.iloc[item["q_now"]]) for item in MONETARY_ITEMS]
        future = [parse_future_choice(row.iloc[item["q_future"]]) for item in MONETARY_ITEMS]

        now_valid = [x for x in now if pd.notna(x)]
        future_valid = [x for x in future if pd.notna(x)]

        for item, c_now, c_future in zip(MONETARY_ITEMS, now, future):
            if pd.isna(c_now) or pd.isna(c_future):
                continue
            if c_now == 0 and c_future == 1:
                kind = "SIR→LDR"
            elif c_now == 1 and c_future == 0:
                kind = "LDR→SIR"
            elif c_now == 0 and c_future == 0:
                kind = "SIR→SIR"
            else:
                kind = "LDR→LDR"
            reversal_rows.append({
                "participant_id": idx + 1,
                "q_now": item["q_now"],
                "q_future": item["q_future"],
                "reversal_type": kind,
            })

        school_choices = [
            parse_school_choice(row.iloc[q]) for q in (22, 23, 24)
        ]
        school_valid = [x for x in school_choices if pd.notna(x)]
        # Number of play/relax-now choices (higher = more procrastination-like choices).
        school_delay_score = (
            float(sum(1 - int(x) for x in school_valid)) if school_valid else np.nan
        )

        participant_rows.append({
            "participant_id": idx + 1,
            "gender": _text(row.iloc[1]),
            "school_level": _text(row.iloc[2]),
            "class": _text(row.iloc[3]),
            "k": score["k"],
            "ln_k": score["ln_k"],
            "consistency": score["consistency"],
            "n_monetary_answered": score["n_answered"],
            "n_best_regions": score["n_best_regions"],
            "reliable_k": score["reliable"],
            "ldr_rate_now": float(np.mean(now_valid)) if now_valid else np.nan,
            "ldr_rate_future": float(np.mean(future_valid)) if future_valid else np.nan,
            "school_delay_score_0_3": school_delay_score,
            "procrastination_likert_1_5": parse_likert(row.iloc[25]),
        })

    participants = pd.DataFrame(participant_rows)
    reversals = pd.DataFrame(reversal_rows)

    # -----------------------
    # Item-level summaries
    # -----------------------
    item_rows = []
    for item in MONETARY_ITEMS:
        now_values = df.iloc[:, item["q_now"]].map(parse_now_choice).dropna().astype(int)
        future_values = df.iloc[:, item["q_future"]].map(parse_future_choice).dropna().astype(int)
        item_rows.append({
            "q_now": item["q_now"],
            "q_future": item["q_future"],
            "small_reward": item["small"],
            "large_reward": item["large"],
            "extra_delay_days": item["delay_days"],
            "k_threshold_now": item["k_threshold"],
            "n_now": len(now_values),
            "ldr_rate_now": now_values.mean(),
            "n_future": len(future_values),
            "ldr_rate_future": future_values.mean(),
        })
    items = pd.DataFrame(item_rows)

    # -----------------------
    # Main paired context test
    # -----------------------
    paired = participants[["ldr_rate_now", "ldr_rate_future"]].dropna()
    paired_test = stats.ttest_rel(paired["ldr_rate_future"], paired["ldr_rate_now"])
    diff = paired["ldr_rate_future"] - paired["ldr_rate_now"]
    mean_diff = float(diff.mean())
    sd_diff = float(diff.std(ddof=1))
    se_diff = sd_diff / math.sqrt(len(diff))
    ci_low, ci_high = stats.t.interval(
        0.95, df=len(diff)-1, loc=mean_diff, scale=se_diff
    )
    cohen_dz = mean_diff / sd_diff

    # -----------------------
    # Reliable-k subset and group tests
    # -----------------------
    reliable = participants[participants["reliable_k"]].copy()

    boys = reliable.loc[reliable["gender"] == "Αγόρι", "ln_k"].dropna().to_numpy(float)
    girls = reliable.loc[reliable["gender"] == "Κορίτσι", "ln_k"].dropna().to_numpy(float)
    gender_test = stats.ttest_ind(boys, girls, equal_var=False)
    gender_df = welch_df(boys, girls)

    gym = reliable.loc[reliable["school_level"] == "Γυμνάσιο", "ln_k"].dropna().to_numpy(float)
    lyc = reliable.loc[reliable["school_level"] == "Λύκειο", "ln_k"].dropna().to_numpy(float)
    school_test = stats.ttest_ind(gym, lyc, equal_var=False)
    school_df = welch_df(gym, lyc)

    # Sensitivity checks using all finite k estimates, not only consistency>=75%.
    all_boys = participants.loc[participants["gender"] == "Αγόρι", "ln_k"].dropna().to_numpy(float)
    all_girls = participants.loc[participants["gender"] == "Κορίτσι", "ln_k"].dropna().to_numpy(float)
    gender_test_all = stats.ttest_ind(all_boys, all_girls, equal_var=False)

    all_gym = participants.loc[participants["school_level"] == "Γυμνάσιο", "ln_k"].dropna().to_numpy(float)
    all_lyc = participants.loc[participants["school_level"] == "Λύκειο", "ln_k"].dropna().to_numpy(float)
    school_test_all = stats.ttest_ind(all_gym, all_lyc, equal_var=False)

    # -----------------------
    # School procrastination block Q22-Q24
    # -----------------------
    school_cols = []
    school_study_rates = []
    for q in (22, 23, 24):
        values = df.iloc[:, q].map(parse_school_choice)
        school_cols.append(values)
        school_study_rates.append(float(values.dropna().mean()))

    school_matrix = pd.concat(school_cols, axis=1).dropna().astype(int).to_numpy()
    cochran_q, cochran_df, cochran_p = cochrans_q(school_matrix)

    # -----------------------
    # Spearman correlations
    # -----------------------
    def spearman(frame: pd.DataFrame, x: str, y: str):
        pair = frame[[x, y]].dropna()
        if len(pair) < 3 or pair[x].nunique() < 2 or pair[y].nunique() < 2:
            return {"n": len(pair), "rho": np.nan, "p": np.nan}
        res = stats.spearmanr(pair[x], pair[y])
        return {"n": len(pair), "rho": float(res.statistic), "p": float(res.pvalue)}

    corr_k_school = spearman(reliable, "ln_k", "school_delay_score_0_3")
    corr_k_likert = spearman(reliable, "ln_k", "procrastination_likert_1_5")
    corr_school_likert = spearman(participants, "school_delay_score_0_3", "procrastination_likert_1_5")

    reversal_counts = reversals["reversal_type"].value_counts().to_dict() if len(reversals) else {}

    summary = {
        "n": int(len(participants)),
        "gender_counts": participants["gender"].replace("", "(missing)").value_counts().to_dict(),
        "school_level_counts": participants["school_level"].replace("", "(missing)").value_counts().to_dict(),
        "reliable_k_n": int(len(reliable)),
        "reliable_k_percent": float(100 * len(reliable) / len(participants)),
        "perfect_consistency_n": int((participants["consistency"] == 1.0).sum()),
        "below_75_consistency_n": int((participants["consistency"] < 0.75).sum()),
        "median_k_reliable": float(reliable["k"].median()),
        "iqr_k_reliable": [float(reliable["k"].quantile(0.25)), float(reliable["k"].quantile(0.75))],
        "ldr_rate_now": float(paired["ldr_rate_now"].mean()),
        "ldr_rate_future": float(paired["ldr_rate_future"].mean()),
        "paired_t": float(paired_test.statistic),
        "paired_df": int(len(paired) - 1),
        "paired_p": float(paired_test.pvalue),
        "mean_change": mean_diff,
        "mean_change_95ci": [float(ci_low), float(ci_high)],
        "cohen_dz": float(cohen_dz),
        "reversal_counts": {k: int(v) for k, v in reversal_counts.items()},
        "gender_test_reliable": {
            "boys_n": int(len(boys)),
            "girls_n": int(len(girls)),
            "boys_mean_ln_k": float(np.mean(boys)),
            "girls_mean_ln_k": float(np.mean(girls)),
            "boys_median_k": float(np.median(np.exp(boys))),
            "girls_median_k": float(np.median(np.exp(girls))),
            "t": float(gender_test.statistic),
            "df": float(gender_df),
            "p": float(gender_test.pvalue),
            "sensitivity_p_all_k": float(gender_test_all.pvalue),
        },
        "school_level_test_reliable": {
            "gymnasium_n": int(len(gym)),
            "lyceum_n": int(len(lyc)),
            "gymnasium_mean_ln_k": float(np.mean(gym)),
            "lyceum_mean_ln_k": float(np.mean(lyc)),
            "gymnasium_median_k": float(np.median(np.exp(gym))),
            "lyceum_median_k": float(np.median(np.exp(lyc))),
            "t": float(school_test.statistic),
            "df": float(school_df),
            "p": float(school_test.pvalue),
            "sensitivity_p_all_k": float(school_test_all.pvalue),
        },
        "school_study_now_rates": {
            "tomorrow": school_study_rates[0],
            "3_days": school_study_rates[1],
            "1_week": school_study_rates[2],
        },
        "cochran_q_school": {
            "q": float(cochran_q), "df": int(cochran_df), "p": float(cochran_p)
        },
        "spearman": {
            "ln_k_vs_school_delay": corr_k_school,
            "ln_k_vs_likert": corr_k_likert,
            "school_delay_vs_likert": corr_school_likert,
        },
    }

    # -----------------------
    # Save tables and summary
    # -----------------------
    participants.to_csv(output_dir / "participant_metrics.csv", index=False, encoding="utf-8-sig")
    items.to_csv(output_dir / "item_summary.csv", index=False, encoding="utf-8-sig")
    reversals.to_csv(output_dir / "preference_reversals.csv", index=False, encoding="utf-8-sig")
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    text_lines = [
        f"N = {summary['n']}",
        f"Reliable k: {summary['reliable_k_n']}/{summary['n']} ({summary['reliable_k_percent']:.1f}%)",
        f"Median k (reliable subset): {summary['median_k_reliable']:.6f}",
        f"LDR now: {100*summary['ldr_rate_now']:.3f}%",
        f"LDR future-shifted: {100*summary['ldr_rate_future']:.3f}%",
        f"Paired t: t({summary['paired_df']})={summary['paired_t']:.4f}, p={summary['paired_p']:.8g}",
        "",
        "Gender (reliable k subset):",
        f"  boys n={len(boys)}, girls n={len(girls)}",
        f"  Welch t={gender_test.statistic:.4f}, df={gender_df:.2f}, p={gender_test.pvalue:.6g}",
        "",
        "School level (reliable k subset):",
        f"  Gymnasium n={len(gym)}, Lyceum n={len(lyc)}",
        f"  Welch t={school_test.statistic:.4f}, df={school_df:.2f}, p={school_test.pvalue:.6g}",
        "",
        "School procrastination Q22-Q24:",
        f"  study-now rates = {[round(100*x, 3) for x in school_study_rates]}",
        f"  Cochran Q={cochran_q:.4f}, df={cochran_df}, p={cochran_p:.8g}",
        "",
        "Spearman correlations:",
        f"  ln(k) vs school delay: rho={corr_k_school['rho']:.4f}, p={corr_k_school['p']:.6g}",
        f"  ln(k) vs Likert: rho={corr_k_likert['rho']:.4f}, p={corr_k_likert['p']:.6g}",
        f"  school delay vs Likert: rho={corr_school_likert['rho']:.4f}, p={corr_school_likert['p']:.6g}",
    ]
    (output_dir / "summary.txt").write_text("\n".join(text_lines), encoding="utf-8")

    # -----------------------
    # Figures
    # -----------------------
    # 1) Consistency
    consistency_counts = [
        int((participants["consistency"] == 1.0).sum()),
        int(((participants["consistency"] >= 0.75) & (participants["consistency"] < 1.0)).sum()),
        int((participants["consistency"] < 0.75).sum()),
    ]
    plt.figure(figsize=(7, 4.5))
    bars = plt.bar(["100%", "75–<100%", "<75%"], consistency_counts)
    plt.ylabel("Participants")
    plt.title("Consistency in Q4–Q12")
    for bar, value in zip(bars, consistency_counts):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, str(value), ha="center")
    plt.tight_layout()
    plt.savefig(output_dir / "consistency.png", dpi=180)
    plt.close()

    # 2) Overall context effect
    overall = [100 * summary["ldr_rate_now"], 100 * summary["ldr_rate_future"]]
    plt.figure(figsize=(7, 4.5))
    bars = plt.bar(["Immediate", "Future-shifted"], overall)
    plt.ylabel("% larger-later choices")
    plt.ylim(0, max(70, max(overall) + 10))
    plt.title("Monetary choices across the two contexts")
    for bar, value in zip(bars, overall):
        plt.text(bar.get_x() + bar.get_width()/2, value + 1, f"{value:.1f}%", ha="center")
    plt.tight_layout()
    plt.savefig(output_dir / "context_overall.png", dpi=180)
    plt.close()

    # 3) Matched items
    x = np.arange(1, len(items) + 1)
    plt.figure(figsize=(8.5, 4.8))
    plt.plot(x, 100 * items["ldr_rate_now"], marker="o", label="Immediate")
    plt.plot(x, 100 * items["ldr_rate_future"], marker="o", label="Future-shifted")
    plt.xticks(x, [f"Q{a}/Q{b}" for a, b in zip(items["q_now"], items["q_future"])])
    plt.xlabel("Matched item pair")
    plt.ylabel("% larger-later choices")
    plt.title("Matched monetary items")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "context_by_item.png", dpi=180)
    plt.close()

    # 4) School study-now rates
    school_pct = 100 * np.asarray(school_study_rates)
    plt.figure(figsize=(7, 4.5))
    bars = plt.bar(["Tomorrow", "3 days", "1 week"], school_pct)
    plt.ylabel("% choosing to study today")
    plt.ylim(0, 100)
    plt.title("School procrastination choices")
    for bar, value in zip(bars, school_pct):
        plt.text(bar.get_x() + bar.get_width()/2, value + 1.5, f"{value:.1f}%", ha="center")
    plt.tight_layout()
    plt.savefig(output_dir / "school_choices.png", dpi=180)
    plt.close()

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("data/stub_responses.xlsx"),
        help="Input Excel workbook (default: data/stub_responses.xlsx)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("outputs/run"),
        help="Output directory (default: outputs/run)",
    )
    parser.add_argument(
        "--min-answered", type=int, default=7,
        help="Minimum number of answered Q4-Q12 items for reliable k (default: 7)",
    )
    args = parser.parse_args()

    summary = run_analysis(args.input, args.output, min_answered=args.min_answered)
    print(f"Analysis complete: {args.output.resolve()}")
    print(
        f"N={summary['n']}; reliable k={summary['reliable_k_n']} "
        f"({summary['reliable_k_percent']:.1f}%); "
        f"LDR {100*summary['ldr_rate_now']:.1f}% -> "
        f"{100*summary['ldr_rate_future']:.1f}%"
    )


if __name__ == "__main__":
    main()
