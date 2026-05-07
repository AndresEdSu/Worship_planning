"""
Metrics module for worship planning evaluation.

Provides functions to calculate participation metrics, coverage scores,
equity measures, and overall plan quality scores.
"""

import pandas as pd
import numpy as np


# ==========
# Utilities
# ==========

def extract_names(cell):
    """
    Extract name from a cell value.
    
    Returns the name if it's a valid string (not empty, not 'Guest'),
    otherwise returns None.
    
    Parameters
    ----------
    cell : str or nan
        Cell value containing a name
        
    Returns
    -------
    str or None
        The name if valid, None otherwise
    """
    if pd.isna(cell):
        return None
    if not isinstance(cell, str):
        return None
    name = cell.strip()
    if not name or name.lower() in {"guest", "invitado"}:
        return None
    return name


def normalize_plan_to_long(df, date_col, role_cols):
    """
    Convert plan DataFrame from wide to long format.
    
    Transforms one row per date into one row per (date, role, person) tuple.
    
    Parameters
    ----------
    df : pd.DataFrame
        Plan data in wide format
    date_col : str
        Name of date column
    role_cols : list
        List of role column names
        
    Returns
    -------
    pd.DataFrame
        Long format with columns: date, role, person
    """
    records = []
    for _, row in df.iterrows():
        date = row[date_col]
        for role in role_cols:
            person = extract_names(row.get(role, np.nan))
            if person:
                records.append({
                    "date": date,
                    "role": "Vocalists"
                    if "vocalist" in role.lower() or "corista" in role.lower()
                    else role,
                    "person": person
                })
    
    return pd.DataFrame(records)


# ==========
# Metric Calculations
# ==========

def calculate_participations(long_df):
    """
    Calculate number of dates each person participated.
    
    Deduplicates by (date, person) to count once per Sunday.
    
    Parameters
    ----------
    long_df : pd.DataFrame
        Long format data
        
    Returns
    -------
    pd.Series
        Participation count by person
    """
    long_unique = long_df.drop_duplicates(["date", "person"])
    return long_unique.groupby("person").size().rename("participations")


def calculate_role_diversity(long_df):
    """
    Calculate number of unique roles per person.
    
    Parameters
    ----------
    long_df : pd.DataFrame
        Long format data
        
    Returns
    -------
    tuple
        (role_diversity Series, roles_list Series)
    """
    role_div = long_df.groupby("person")["role"].nunique().rename("role_diversity")
    role_list = long_df.groupby("person")["role"].apply(
        lambda s: ", ".join(sorted(set(s)))
    ).rename("roles")
    return role_div, role_list


def calculate_max_consecutive_weeks(long_df):
    """
    Calculate longest consecutive week streak per person.
    
    Parameters
    ----------
    long_df : pd.DataFrame
        Long format data
        
    Returns
    -------
    pd.Series
        Max consecutive weeks by person
    """
    long_unique = long_df.drop_duplicates(["date", "person"])
    person_dates = long_unique.groupby("person")["date"].apply(
        lambda s: sorted(set(s))
    ).to_dict()
    
    max_consec = {}
    for person, dates in person_dates.items():
        if not dates:
            max_consec[person] = 0
            continue
        best = cur = 1
        for i in range(1, len(dates)):
            if (dates[i] - dates[i - 1]).days == 7:
                cur += 1
                best = max(best, cur)
            else:
                cur = 1
        max_consec[person] = best
    
    return pd.Series(max_consec, name="max_consecutive_weeks")


def calculate_coverage_score(df, date_col, role_cols):
    """
    Calculate coverage score for plan.
    
    Measures percentage of role slots filled.
    
    Parameters
    ----------
    df : pd.DataFrame
        Plan data
    date_col : str
        Date column name
    role_cols : list
        Role column names
        
    Returns
    -------
    tuple
        (coverage_score, missing_total, missing_max, missing_by_date DataFrame)
    """
    missing_by_date = []
    for _, row in df.iterrows():
        date = row[date_col]
        missing = 0
        for role in role_cols:
            name = extract_names(row.get(role, np.nan))
            if name is None:
                missing += 1
        missing_by_date.append({"date": date, "missing_core_roles": missing})
    
    missing_by_date_df = pd.DataFrame(missing_by_date)
    n_dates = df[date_col].nunique()
    n_core_roles = len(role_cols)
    missing_total = int(missing_by_date_df["missing_core_roles"].sum())
    missing_max = int(missing_by_date_df["missing_core_roles"].max())
    
    coverage_score = 100 * (1 - missing_total / (n_dates * n_core_roles))
    coverage_score = float(np.clip(coverage_score, 0, 100))
    
    return coverage_score, missing_total, missing_max, missing_by_date_df


def calculate_resilience_score(long_df, critical_roles):
    """
    Calculate resilience score.
    
    Measures how distributed critical roles are (lower concentration = higher resilience).
    
    Parameters
    ----------
    long_df : pd.DataFrame
        Long format data
    critical_roles : list
        List of critical role names
        
    Returns
    -------
    float
        Resilience score (0-100)
    """
    top_shares = []
    for role in critical_roles:
        role_long = long_df[long_df["role"] == role]
        if len(role_long) == 0:
            continue
        counts = role_long["person"].value_counts()
        top_share = counts.iloc[0] / counts.sum()
        top_shares.append(top_share)
    
    avg_top_share = float(np.mean(top_shares)) if top_shares else 1.0
    resilience_score = 100 * (1 - avg_top_share)
    resilience_score = float(np.clip(resilience_score, 0, 100))
    
    return resilience_score, avg_top_share


def calculate_equity_score(participations):
    """
    Calculate equity score.
    
    Measures balance in participation distribution (lower variance = higher equity).
    
    Parameters
    ----------
    participations : pd.Series
        Participation count per person
        
    Returns
    -------
    tuple
        (equity_score, coefficient_of_variation)
    """
    mean_p = float(participations.mean()) if len(participations) else 0.0
    std_p = float(participations.std(ddof=0)) if len(participations) else 0.0
    cv = (std_p / mean_p) if mean_p > 0 else 1.0
    
    equity_score = 100 * (1 - min(cv, 1.0))
    equity_score = float(np.clip(equity_score, 0, 100))
    
    return equity_score, cv


def calculate_rest_score(max_consecutive_weeks):
    """
    Calculate rest score.
    
    Measures adequate spacing between consecutive participations.
    
    Parameters
    ----------
    max_consecutive_weeks : pd.Series
        Max consecutive weeks per person
        
    Returns
    -------
    tuple
        (rest_score, avg_max_consecutive)
    """
    avg_max_consec = float(max_consecutive_weeks.mean()) if len(max_consecutive_weeks) else 0.0
    rest_score = 100 - 25 * max(0, (avg_max_consec - 2))
    rest_score = float(np.clip(rest_score, 0, 100))
    
    return rest_score, avg_max_consec


def calculate_overall_score(coverage_score, equity_score, rest_score, resilience_score,
                           w_coverage=0.35, w_equity=0.30, w_rest=0.20, w_resilience=0.15):
    """
    Calculate overall plan quality score.
    
    Weighted combination of component scores.
    
    Parameters
    ----------
    coverage_score : float
        Coverage metric
    equity_score : float
        Equity metric
    rest_score : float
        Rest metric
    resilience_score : float
        Resilience metric
    w_coverage : float
        Weight for coverage (default 0.35)
    w_equity : float
        Weight for equity (default 0.30)
    w_rest : float
        Weight for rest (default 0.20)
    w_resilience : float
        Weight for resilience (default 0.15)
        
    Returns
    -------
    float
        Overall score (0-100)
    """
    overall_score = (
        w_coverage * coverage_score
        + w_equity * equity_score
        + w_rest * rest_score
        + w_resilience * resilience_score
    )
    return float(overall_score)


def evaluate_plan(df, date_col, role_cols, critical_roles, weights=None):
    """
    Comprehensive plan evaluation.
    
    Calculates all metrics and returns summary.
    
    Parameters
    ----------
    df : pd.DataFrame
        Plan data
    date_col : str
        Date column name
    role_cols : list
        Role column names
    critical_roles : list
        Critical role names for resilience
    weights : dict, optional
        Weights for overall score {coverage, equity, rest, resilience}
        
    Returns
    -------
    dict
        Dictionary with all metrics
    """
    if weights is None:
        weights = {
            'coverage': 0.35,
            'equity': 0.30,
            'rest': 0.20,
            'resilience': 0.15
        }
    
    # Normalize to long format
    long = normalize_plan_to_long(df, date_col, role_cols)
    
    # Calculate all metrics
    participations = calculate_participations(long)
    role_div, role_list = calculate_role_diversity(long)
    max_consec = calculate_max_consecutive_weeks(long)
    coverage_score, missing_total, missing_max, missing_by_date = calculate_coverage_score(
        df, date_col, role_cols
    )
    resilience_score, avg_top_share = calculate_resilience_score(long, critical_roles)
    equity_score, cv = calculate_equity_score(participations)
    rest_score, avg_max_consec = calculate_rest_score(max_consec)
    
    overall_score = calculate_overall_score(
        coverage_score, equity_score, rest_score, resilience_score,
        w_coverage=weights['coverage'],
        w_equity=weights['equity'],
        w_rest=weights['rest'],
        w_resilience=weights['resilience']
    )
    
    # Build participant summary
    participants = pd.concat([participations, role_div, role_list, max_consec], axis=1)
    participants = participants.fillna(0).sort_values(["participations"], ascending=False)
    
    
    score_metrics = {
        "overall_score": overall_score,
        "coverage_score": coverage_score,
        "equity_score": equity_score,
        "rest_score": rest_score,
        "resilience_score": resilience_score
    }
    other_metrics = {
        'num_dates': df[date_col].nunique(),
        'num_core_roles': len(role_cols),
        'missing_total': missing_total,
        'missing_max': missing_max,
        'participation_cv': cv,
        'avg_critical_top_share': avg_top_share,
        "avg_max_consecutive_weeks": avg_max_consec
    }
    
    metrics = {
        'score_metrics': score_metrics,
        'other_metrics': other_metrics
    }
    
    dfs = {
        'missing_by_date': missing_by_date,
        'participants': participants,
        'long_format': long
    }
    
    result = {'metrics': metrics, 'dfs': dfs}

    return result
