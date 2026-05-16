from __future__ import annotations

from dataclasses import dataclass
from html import escape

import pandas as pd

from src.planning.schema import (
    BASSIST_COL,
    DIRECTOR_COL,
    DRUMMER_COL,
    GUITARIST_COL,
    KEYBOARDIST_COL,
    REHEARSAL_DATE_COL as DATE_REHEARSAL_COL,
    REHEARSAL_TIME_COL,
    SERVICE_DATE_COL as DATE_PRESENTATION_COL,
    VOCALIST_1_COL,
    VOCALIST_2_COL,
    VOCALISTS_COL,
)

MONTHS = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

@dataclass(frozen=True)
class HtmlTheme:
    page_bg: str = "#f4f6f8"
    ink: str = "#14181f"
    ink_soft: str = "#515765"
    ink_muted: str = "#6e7686"
    header_bg: str = "#14181f"
    accent: str = "#ebc850"
    card_bg: str = "#ffffff"
    card_border: str = "#e5e8ee"


def _is_missing(value: object) -> bool:
    return value is None or pd.isna(value) or not str(value).strip()


def _clean_display_text(value: object) -> str | None:
    if _is_missing(value):
        return None
    return " ".join(str(value).strip().split())


def _combine_vocalists(row: pd.Series) -> str | None:
    if VOCALISTS_COL in row.index and not _is_missing(row.get(VOCALISTS_COL)):
        return _clean_display_text(row.get(VOCALISTS_COL))

    vocalist_values: list[str] = []
    for column in (VOCALIST_1_COL, VOCALIST_2_COL):
        value = _clean_display_text(row.get(column))
        if value and value not in vocalist_values:
            vocalist_values.append(value)
    if not vocalist_values:
        return None
    return ", ".join(vocalist_values)


def prepare_infographic_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    plan = df.copy()

    required_columns = {
        DATE_REHEARSAL_COL,
        DATE_PRESENTATION_COL,
        REHEARSAL_TIME_COL,
        DIRECTOR_COL,
        GUITARIST_COL,
        DRUMMER_COL,
        BASSIST_COL,
        KEYBOARDIST_COL,
    }
    missing_columns = sorted(required_columns - set(plan.columns))
    if missing_columns:
        missing_display = ", ".join(missing_columns)
        raise ValueError(f"Missing required columns for infographic export: {missing_display}")

    if plan[DATE_REHEARSAL_COL].isna().any() or plan[DATE_PRESENTATION_COL].isna().any():
        raise ValueError("Some infographic dates are missing or invalid.")

    plan[VOCALISTS_COL] = plan.apply(_combine_vocalists, axis=1)

    return plan


def format_date(value: pd.Timestamp) -> str:
    date_value = pd.Timestamp(value)
    return f"{MONTHS[date_value.month]} {date_value.day}, {date_value.year}"


def format_month_year(value: pd.Timestamp) -> str:
    date_value = pd.Timestamp(value)
    return f"{MONTHS[date_value.month]} {date_value.year}"


def _strip_trailing_whitespace(content: str) -> str:
    return "\n".join(line.rstrip() for line in content.splitlines()) + "\n"


def _role_pairs(row: pd.Series) -> list[tuple[str, str]]:
    pairs = [
        ("Director", row.get(DIRECTOR_COL)),
        ("Guitar", row.get(GUITARIST_COL)),
        ("Drums", row.get(DRUMMER_COL)),
        ("Bass", row.get(BASSIST_COL)),
        ("Keyboard", row.get(KEYBOARDIST_COL)),
        ("Vocalists", row.get(VOCALISTS_COL)),
    ]
    return [(label, str(value)) for label, value in pairs if not _is_missing(value)]


def _group_rows_by_service_month(plan_df: pd.DataFrame) -> list[tuple[str, list[pd.Series]]]:
    sorted_rows = sorted(
        (plan_df.iloc[index] for index in range(len(plan_df))),
        key=lambda row: pd.Timestamp(row[DATE_PRESENTATION_COL]),
    )

    pages: list[tuple[str, list[pd.Series]]] = []
    current_month_key: tuple[int, int] | None = None
    current_month_label = ""
    current_rows: list[pd.Series] = []

    for row in sorted_rows:
        service_date = pd.Timestamp(row[DATE_PRESENTATION_COL])
        month_key = (service_date.year, service_date.month)

        if current_month_key is not None and month_key != current_month_key:
            pages.append((current_month_label, current_rows))
            current_rows = []

        current_month_key = month_key
        current_month_label = format_month_year(service_date)
        current_rows.append(row)

    if current_rows:
        pages.append((current_month_label, current_rows))

    return pages


def _render_card(row: pd.Series) -> str:
    role_items = "\n".join(
        f"""
        <div class="role-row">
          <div class="role-label">{escape(label)}</div>
          <div class="role-value">{escape(value)}</div>
        </div>
        """
        for label, value in _role_pairs(row)
    )

    rehearsal_time = row.get(REHEARSAL_TIME_COL)
    rehearsal_time_html = (
        f'<div class="card-time">{escape(str(rehearsal_time))}</div>'
        if not _is_missing(rehearsal_time)
        else ""
    )

    return f"""
    <article class="plan-card">
      <div class="card-dates">
        <div class="date-block">
          <div class="date-label">Rehearsal</div>
          <div class="date-value">{escape(format_date(row[DATE_REHEARSAL_COL]))}</div>
          {rehearsal_time_html}
        </div>
        <div class="date-block">
          <div class="date-label">Service</div>
          <div class="date-value">{escape(format_date(row[DATE_PRESENTATION_COL]))}</div>
        </div>
      </div>
      <div class="card-roles">
        {role_items}
      </div>
    </article>
    """


def render_infographic_html(
    plan_df: pd.DataFrame,
    *,
    title: str,
    theme: HtmlTheme | None = None,
) -> str:
    html_theme = theme or HtmlTheme()
    pages = _group_rows_by_service_month(plan_df)

    page_sections = []
    total_pages = len(pages)
    for page_index, (month_label, page_rows) in enumerate(pages, start=1):
        cards_html = "\n".join(_render_card(row) for row in page_rows)
        page_sections.append(
            f"""
            <section class="page">
              <header class="page-header">
                <div>
                  <h1>{escape(title)}</h1>
                  <p>{escape(month_label)}</p>
                </div>
                <div class="page-number">Page {page_index}/{total_pages}</div>
              </header>
              <div class="page-body">
                {cards_html}
              </div>
            </section>
            """
        )

    styles = f"""
    :root {{
      --page-bg: {html_theme.page_bg};
      --ink: {html_theme.ink};
      --ink-soft: {html_theme.ink_soft};
      --ink-muted: {html_theme.ink_muted};
      --header-bg: {html_theme.header_bg};
      --accent: {html_theme.accent};
      --card-bg: {html_theme.card_bg};
      --card-border: {html_theme.card_border};
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      padding: 32px;
      background: var(--page-bg);
      color: var(--ink);
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    }}

    .document {{
      display: grid;
      gap: 32px;
    }}

    .page {{
      width: min(100%, 1100px);
      margin: 0 auto;
      background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
      border: 1px solid var(--card-border);
      border-radius: 28px;
      overflow: hidden;
      box-shadow: 0 24px 70px rgba(20, 24, 31, 0.08);
      page-break-after: always;
    }}

    .page:last-child {{
      page-break-after: auto;
    }}

    .page-header {{
      background: var(--header-bg);
      color: #ffffff;
      padding: 36px 40px 28px;
      border-bottom: 10px solid var(--accent);
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: end;
    }}

    .page-header h1 {{
      margin: 0;
      font-size: 2rem;
      line-height: 1.1;
      white-space: pre-line;
    }}

    .page-header p {{
      margin: 10px 0 0;
      color: rgba(255, 255, 255, 0.82);
      font-size: 1rem;
    }}

    .page-number {{
      font-size: 0.95rem;
      color: rgba(255, 255, 255, 0.88);
      white-space: nowrap;
    }}

    .page-body {{
      padding: 32px;
      display: grid;
      gap: 20px;
    }}

    .plan-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 22px;
      padding: 24px;
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 24px;
    }}

    .card-dates {{
      display: grid;
      gap: 18px;
      align-content: start;
      padding-right: 20px;
      border-right: 1px solid var(--card-border);
    }}

    .date-block {{
      display: grid;
      gap: 6px;
    }}

    .date-label {{
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.8rem;
      color: var(--ink-muted);
      font-weight: 700;
    }}

    .date-value {{
      font-size: 1.45rem;
      line-height: 1.15;
      font-weight: 700;
      color: var(--ink);
    }}

    .card-time {{
      color: var(--ink-soft);
      font-size: 0.95rem;
    }}

    .card-roles {{
      display: grid;
      gap: 12px;
      align-content: start;
    }}

    .role-row {{
      display: grid;
      grid-template-columns: 130px 1fr;
      gap: 16px;
      align-items: start;
      padding-bottom: 10px;
      border-bottom: 1px solid #f0f2f5;
    }}

    .role-row:last-child {{
      border-bottom: none;
      padding-bottom: 0;
    }}

    .role-label {{
      font-weight: 700;
      color: var(--ink);
    }}

    .role-value {{
      color: var(--ink-soft);
      line-height: 1.45;
      word-break: break-word;
    }}

    @media (max-width: 760px) {{
      body {{
        padding: 16px;
      }}

      .page-header {{
        padding: 28px 22px 20px;
        flex-direction: column;
        align-items: start;
      }}

      .page-body {{
        padding: 18px;
      }}

      .plan-card {{
        grid-template-columns: 1fr;
      }}

      .card-dates {{
        border-right: none;
        padding-right: 0;
        padding-bottom: 16px;
        border-bottom: 1px solid var(--card-border);
      }}

      .role-row {{
        grid-template-columns: 1fr;
        gap: 6px;
      }}
    }}

    @media print {{
      body {{
        padding: 0;
        background: #ffffff;
      }}

      .page {{
        width: 100%;
        border: none;
        border-radius: 0;
        box-shadow: none;
        break-inside: avoid;
      }}
    }}
    """

    return _strip_trailing_whitespace(f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title.replace(chr(10), " "))}</title>
    <style>
    {styles}
    </style>
  </head>
  <body>
    <main class="document">
      {''.join(page_sections)}
    </main>
  </body>
</html>
""")


def build_plan_infographic_html(
    plan_df: pd.DataFrame,
    *,
    title: str = "Worship Planning",
    theme: HtmlTheme | None = None,
) -> str:
    prepared_plan_df = prepare_infographic_dataframe(plan_df)

    return render_infographic_html(
        prepared_plan_df,
        title=title,
        theme=theme,
    )
