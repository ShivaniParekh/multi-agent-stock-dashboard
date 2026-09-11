from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.sax.saxutils import escape


HEADERS = [
    "Suggested At (IST)",
    "Run ID",
    "Mode",
    "Engine",
    "Symbol",
    "Name",
    "Cap",
    "Sector",
    "Verdict",
    "Confidence",
    "Winner",
    "Why",
    "Key Catalyst",
    "Live Price",
    "Day Change %",
    "Volume",
    "52W High",
    "52W Low",
    "52W Position %",
    "% From 52W High",
    "RVOL",
    "Price vs SMA %",
    "Window Return %",
    "Swing High",
    "Swing Low",
    "Day Range Position %",
    "Trend",
    "Analyst Consensus",
    "Analysts",
    "Buy %",
    "Hold %",
    "Sell %",
    "Target Mean",
    "Target Low",
    "Target High",
    "Analyst Upside %",
    "News Total",
    "Positive News",
    "Negative News",
    "Neutral News",
    "Primary Pattern",
    "Pattern Status",
    "Pattern Confidence",
    "Entry Low",
    "Entry High",
    "Entry Style",
    "Target 1",
    "Target 1 Time",
    "Target 2",
    "Target 2 Time",
    "Target 3",
    "Target 3 Time",
    "Invalidation",
    "Data Gaps",
    "Bull Score",
    "Bear Score",
    "Net",
    "Bull Reasons",
    "Bear Reasons",
    "Chart URL",
    "Evidence JSON",
    "Analysis JSON",
]


def _column_name(number: int) -> str:
    result = ""

    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result

    return result


def _cell_ref(row: int, col: int) -> str:
    return f"{_column_name(col)}{row}"


def _xml_cell(row: int, col: int, value, header=False):

    ref = _cell_ref(row, col)

    if value is None:
        value = ""

    style = ' s="1"' if header else ""

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'

    text = escape(str(value))

    return (
        f'<c r="{ref}"{style} t="inlineStr">'
        f"<is><t xml:space=\"preserve\">{text}</t></is>"
        f"</c>"
    )


def _rows_xml(rows):

    output = []

    for row_number, row in enumerate(rows, start=1):

        cells = []

        for col_number, value in enumerate(row, start=1):

            if value in (None, ""):
                continue

            cells.append(
                _xml_cell(
                    row_number,
                    col_number,
                    value,
                    header=(row_number == 1),
                )
            )

        output.append(
            f'<row r="{row_number}">'
            f'{"".join(cells)}'
            f"</row>"
        )

    return "".join(output)


def _safe_sheet_name(name):

    return re.sub(
        r'[\\/*?:\[\]]',
        "_",
        name
    )[:31]


def _write_xlsx(path: Path, sheets: dict[str, list[list]]):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    sheet_items = list(sheets.items())

    workbook_sheets = []
    relationships = []

    for index, (name, _) in enumerate(
        sheet_items,
        start=1
    ):

        workbook_sheets.append(
            f'<sheet '
            f'name="{escape(_safe_sheet_name(name))}" '
            f'sheetId="{index}" '
            f'r:id="rId{index}"/>'
        )

        relationships.append(
            f'<Relationship '
            f'Id="rId{index}" '
            f'Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook '
        'xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships">'
        '<sheets>'
        + "".join(workbook_sheets)
        + "</sheets>"
        "</workbook>"
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships '
        'xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">'
        + "".join(relationships)
        +
        '<Relationship '
        'Id="rIdStyles" '
        'Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )

    overrides = []

    for index in range(
        1,
        len(sheet_items) + 1
    ):

        overrides.append(
            f'<Override '
            f'PartName="/xl/worksheets/sheet{index}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.'
            f'spreadsheetml.worksheet+xml"/>'
        )

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types '
        'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" '
        'ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.styles+xml"/>'
        + "".join(overrides)
        + "</Types>"
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'

        '<fonts count="3">'
        '<font><sz val="11"/><name val="Aptos"/></font>'
        '<font><b/><sz val="11"/><name val="Aptos"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/>'
        '<sz val="11"/><name val="Aptos"/></font>'
        "</fonts>"

        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid">'
        '<fgColor rgb="FF172033"/>'
        '<bgColor indexed="64"/>'
        "</patternFill></fill>"
        "</fills>"

        '<borders count="1">'
        "<border><left/><right/><top/><bottom/><diagonal/></border>"
        "</borders>"

        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"

        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        '<xf numFmtId="0" fontId="2" fillId="2" '
        'borderId="0" applyFont="1" applyFill="1"/>'
        "</cellXfs>"

        '<cellStyles count="1">'
        '<cellStyle name="Normal" xfId="0" builtinId="0"/>'
        "</cellStyles>"

        "</styleSheet>"
    )

    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED
    ) as archive:

        archive.writestr(
            "[Content_Types].xml",
            content_types
        )

        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/'
            'relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        )

        archive.writestr(
            "xl/workbook.xml",
            workbook_xml
        )

        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            workbook_rels
        )

        archive.writestr(
            "xl/styles.xml",
            styles_xml
        )

        for index, (_, rows) in enumerate(
            sheet_items,
            start=1
        ):

            max_columns = max(
                (len(row) for row in rows),
                default=1
            )

            sheet_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet '
                'xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main">'
                f'<cols>'
                f'<col min="1" max="{max_columns}" '
                f'width="18" customWidth="1"/>'
                f'</cols>'
                f'<sheetData>'
                f'{_rows_xml(rows)}'
                f'</sheetData>'
                '</worksheet>'
            )

            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                sheet_xml
            )


def flatten_verdict(
    row,
    run_id,
    mode,
    evidence,
    analysis,
    suggested_at
):

    v = analysis.get("verdict", {})
    scores = analysis.get("scores", {})

    price = evidence.get("price", {})
    ranges = evidence.get("range_52w", {})
    technicals = evidence.get("technicals", {})
    analyst = evidence.get("analyst", {})
    news = evidence.get("news", {})
    patterns = evidence.get("patterns", {})

    primary_pattern = patterns.get("primary") or {}

    trade_plan = (
        analysis.get("trade_plan")
        or {}
    )

    entry = (
        trade_plan.get("entry")
        or {}
    )

    targets = (
        trade_plan.get("targets")
        or []
    )

    target_map = {
        item.get("label"): item
        for item in targets
        if isinstance(item, dict)
    }

    symbol = evidence.get(
        "symbol",
        row.get("symbol", "")
    )

    chart_url = (
        "https://www.tradingview.com/"
        f"symbols/NSE-{symbol}/"
    )

    return [
        suggested_at,
        run_id,
        mode,
        row.get("engine", ""),
        symbol,
        evidence.get("name", ""),
        evidence.get("cap_segment", ""),
        evidence.get("sector", ""),
        v.get("verdict", row.get("verdict", "")),
        v.get("confidence", row.get("confidence", "")),
        v.get("winner", row.get("winner", "")),
        v.get("rationale", row.get("why", "")),
        v.get("key_catalyst", row.get("catalyst", "")),
        price.get("live", row.get("price")),
        price.get(
            "day_change_pct",
            row.get("day_change_pct")
        ),
        price.get("volume"),
        ranges.get("high"),
        ranges.get("low"),
        ranges.get("position_pct"),
        ranges.get("pct_from_high"),
        technicals.get("rvol"),
        technicals.get("price_vs_sma_pct"),
        technicals.get("window_return_pct"),
        technicals.get("swing_high"),
        technicals.get("swing_low"),
        technicals.get("day_range_position_pct"),
        technicals.get("trend"),
        analyst.get("consensus"),
        analyst.get("num_analysts"),
        analyst.get("buy_pct"),
        analyst.get("hold_pct"),
        analyst.get("sell_pct"),
        analyst.get("target_mean"),
        analyst.get("target_low"),
        analyst.get("target_high"),
        analyst.get("upside_pct"),
        news.get("total"),
        news.get("positive"),
        news.get("negative"),
        news.get("neutral"),
        primary_pattern.get("pattern"),
        primary_pattern.get("status"),
        primary_pattern.get("confidence"),
        entry.get("low"),
        entry.get("high"),
        trade_plan.get("style"),
        target_map.get(
            "Target 1",
            {}
        ).get("price"),
        target_map.get(
            "Target 1",
            {}
        ).get("time"),
        target_map.get(
            "Target 2",
            {}
        ).get("price"),
        target_map.get(
            "Target 2",
            {}
        ).get("time"),
        target_map.get(
            "Target 3",
            {}
        ).get("price"),
        target_map.get(
            "Target 3",
            {}
        ).get("time"),
        trade_plan.get("invalidation"),
        ", ".join(
            evidence.get("data_gaps", [])
            or []
        ),
        scores.get(
            "bull",
            {}
        ).get("score"),
        scores.get(
            "bear",
            {}
        ).get("score"),
        v.get("net"),
        "; ".join(
            scores.get(
                "bull",
                {}
            ).get("reasons", [])
            or []
        ),
        "; ".join(
            scores.get(
                "bear",
                {}
            ).get("reasons", [])
            or []
        ),
        chart_url,
        json.dumps(
            evidence,
            ensure_ascii=False,
            separators=(",", ":")
        ),
        json.dumps(
            analysis,
            ensure_ascii=False,
            separators=(",", ":")
        ),
    ]


def export_suggestions(
    rows,
    output_path
):

    output_path = Path(output_path)

    headers = [HEADERS]

    data_rows = []

    run_summary = {
        "headers": [
            "Run ID",
            "Suggested At (IST)",
            "Mode",
            "Engine",
            "Stocks",
            "BUY Signals",
        ],
        "rows": []
    }

    run_data = {}

    for row in rows:

        payload = row.get("payload") or {}

        if isinstance(payload, str):

            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}

        evidence = payload.get(
            "evidence",
            {}
        )

        analysis = payload.get(
            "analysis",
            payload
        )

        suggested_at = (
            row.get("suggested_at")
            or row.get("started_at")
            or ""
        )

        data_rows.append(
            flatten_verdict(
                row=row,
                run_id=row.get("run_id"),
                mode=row.get("mode", ""),
                evidence=evidence,
                analysis=analysis,
                suggested_at=suggested_at,
            )
        )

        run_id = row.get("run_id")

        if run_id not in run_data:

            run_data[run_id] = {
                "suggested_at": suggested_at,
                "mode": row.get("mode", ""),
                "engine": row.get("engine", ""),
                "stocks": 0,
                "buy": 0,
            }

        run_data[run_id]["stocks"] += 1

        if row.get("verdict") == "BUY":
            run_data[run_id]["buy"] += 1

    for run_id, data in sorted(
        run_data.items()
    ):

        run_summary["rows"].append([
            run_id,
            data["suggested_at"],
            data["mode"],
            data["engine"],
            data["stocks"],
            data["buy"],
        ])

    suggestions_sheet = headers + data_rows

    summary_sheet = [
        [
            "Exported At (IST)",
            datetime.now(
                timezone(
                    timedelta(hours=5, minutes=30)
                )
            ).strftime(
                "%Y-%m-%d %H:%M:%S IST"
            )
        ],
        [
            "Total Stock Suggestions",
            len(data_rows)
        ],
        [],
        run_summary["headers"],
        *run_summary["rows"],
    ]

    _write_xlsx(
        output_path,
        {
            "Stock Suggestions": suggestions_sheet,
            "Run Summary": summary_sheet,
        }
    )

    return output_path