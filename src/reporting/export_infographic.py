from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable

import pandas as pd


DATE_REHEARSAL_COL = "Fecha Ensayo (Sabado)"
DATE_PRESENTATION_COL = "Fecha Presentacion (Domingo)"
DATE_REHEARSAL_ALIASES = ("Fecha Ensayo (Sabado)", "Fecha Ensayo (Sábado)")
DATE_PRESENTATION_ALIASES = (
    "Fecha Presentacion (Domingo)",
    "Fecha Presentación (Domingo)",
)
REHEARSAL_TIME_COL = "Horario Tentativo de Ensayo"
ROLE_SOURCE_COLUMNS = (
    "Director",
    "Guitarrista",
    "Baterista",
    "Bajista",
    "Tecladista",
    "Corista_1",
    "Corista_2",
    "Coristas",
)
MONTHS_ES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
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


def _canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    column_map = {}
    for alias in DATE_REHEARSAL_ALIASES:
        if alias in df.columns:
            column_map[alias] = DATE_REHEARSAL_COL
    for alias in DATE_PRESENTATION_ALIASES:
        if alias in df.columns:
            column_map[alias] = DATE_PRESENTATION_COL
    return df.rename(columns=column_map)


def _is_missing(value: object) -> bool:
    return value is None or pd.isna(value) or not str(value).strip()


def _clean_display_text(value: object) -> str | None:
    if _is_missing(value):
        return None
    return " ".join(str(value).strip().split())


def _combine_choirs(row: pd.Series) -> str | None:
    if "Coristas" in row.index and not _is_missing(row.get("Coristas")):
        return _clean_display_text(row.get("Coristas"))

    choir_values: list[str] = []
    for column in ("Corista_1", "Corista_2"):
        value = _clean_display_text(row.get(column))
        if value and value not in choir_values:
            choir_values.append(value)
    if not choir_values:
        return None
    return ", ".join(choir_values)


def prepare_infographic_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    plan = _canonicalize_columns(df.copy())

    required_columns = {
        DATE_REHEARSAL_COL,
        DATE_PRESENTATION_COL,
        REHEARSAL_TIME_COL,
        "Director",
        "Guitarrista",
        "Baterista",
        "Bajista",
        "Tecladista",
    }
    missing_columns = sorted(required_columns - set(plan.columns))
    if missing_columns:
        missing_display = ", ".join(missing_columns)
        raise ValueError(f"Missing required columns for infographic export: {missing_display}")

    if plan[DATE_REHEARSAL_COL].isna().any() or plan[DATE_PRESENTATION_COL].isna().any():
        raise ValueError("Some infographic dates are missing or invalid.")

    plan["Coristas"] = plan.apply(_combine_choirs, axis=1)
    
    return plan

def format_date_es(value: pd.Timestamp) -> str:
    date_value = pd.Timestamp(value)
    return f"{date_value.day} {MONTHS_ES[date_value.month]} {date_value.year}"


def _role_pairs(row: pd.Series) -> list[tuple[str, str]]:
    pairs = [
        ("Director", row.get("Director")),
        ("Guitarra", row.get("Guitarrista")),
        ("Batería", row.get("Baterista")),
        ("Bajo", row.get("Bajista")),
        ("Teclado", row.get("Tecladista")),
        ("Coristas", row.get("Coristas")),
    ]
    return [(label, str(value)) for label, value in pairs if not _is_missing(value)]


def _chunk_rows(rows: Iterable[pd.Series], chunk_size: int) -> list[list[pd.Series]]:
    pages: list[list[pd.Series]] = []
    current_page: list[pd.Series] = []

    for row in rows:
        current_page.append(row)
        if len(current_page) == chunk_size:
            pages.append(current_page)
            current_page = []

    if current_page:
        pages.append(current_page)

    return pages or [[]]


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
          <div class="date-label">Ensayo</div>
          <div class="date-value">{escape(format_date_es(row[DATE_REHEARSAL_COL]))}</div>
          {rehearsal_time_html}
        </div>
        <div class="date-block">
          <div class="date-label">Presentación</div>
          <div class="date-value">{escape(format_date_es(row[DATE_PRESENTATION_COL]))}</div>
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
    cards_per_page: int = 4,
    theme: HtmlTheme | None = None,
) -> str:
    html_theme = theme or HtmlTheme()
    plan_rows = [plan_df.iloc[index] for index in range(len(plan_df))]
    pages = _chunk_rows(plan_rows, cards_per_page)
    subtitle = (
        f"{format_date_es(plan_df[DATE_PRESENTATION_COL].min())} a "
        f"{format_date_es(plan_df[DATE_PRESENTATION_COL].max())}"
    )

    page_sections = []
    total_pages = len(pages)
    for page_index, page_rows in enumerate(pages, start=1):
        cards_html = "\n".join(_render_card(row) for row in page_rows)
        page_sections.append(
            f"""
            <section class="page">
              <header class="page-header">
                <div>
                  <h1>{escape(title)}</h1>
                  <p>{escape(subtitle)}</p>
                </div>
                <div class="page-number">Página {page_index}/{total_pages}</div>
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

    return f"""<!DOCTYPE html>
<html lang="es">
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
"""


def build_plan_infographic_html(
    plan_df: pd.DataFrame,
    *,
    title: str = "Planificación de\nMinisterio de Adoración Ágape",
    cards_per_page: int = 4,
    theme: HtmlTheme | None = None,
) -> str:
    prepared_plan_df = prepare_infographic_dataframe(plan_df)

    return render_infographic_html(
        prepared_plan_df,
        title=title,
        cards_per_page=cards_per_page,
        theme=theme,
    )
