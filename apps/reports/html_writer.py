from django.utils import timezone

_PRINT_CSS = """
@page {
    size: A4 landscape;
    margin: 1.5cm 1.2cm 1.8cm 1.2cm;

    @bottom-right {
        content: "Page " counter(page) " of " counter(pages);
        font-family: Georgia, serif;
        font-size: 9pt;
        color: #555;
    }

    @bottom-left {
        content: "CONFIDENTIAL";
        font-family: Georgia, serif;
        font-size: 8pt;
        color: #888;
    }
}

html, body {
    counter-reset: pages;
}

body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 10pt;
    line-height: 1.35;
    color: #111;
    background: #fff;
    margin: 0;
    padding: 0;
}

h1, h2, h3, h4 {
    page-break-after: avoid;
    font-family: Georgia, serif;
    color: #1a1a1a;
}

h1 {
    font-size: 18pt;
    border-bottom: 2px solid #1f3a68;
    padding-bottom: 4pt;
    margin-bottom: 6pt;
}

h2 {
    font-size: 13pt;
    margin-top: 14pt;
    margin-bottom: 6pt;
    color: #1f3a68;
    border-bottom: 1px solid #cfd8e8;
    padding-bottom: 2pt;
}

h3 {
    font-size: 11pt;
    margin-top: 10pt;
    margin-bottom: 4pt;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 6pt 0 10pt 0;
    font-size: 9.5pt;
}

thead { display: table-header-group; }

tfoot {
    display: table-footer-group;
}

thead th {
    background-color: #1f3a68;
    color: #ffffff;
    font-weight: bold;
    padding: 6pt 8pt;
    border: 1px solid #152a4b;
    text-align: left;
}

tbody td, tfoot td {
    padding: 5pt 8pt;
    border: 1px solid #b8c4d8;
    vertical-align: top;
}

tbody tr:nth-child(even) td {
    background-color: #f5f7fb;
}

tbody tr.action-row {
    page-break-inside: avoid;
}

tbody tr.subtotal td, tfoot td {
    background-color: #e6ecf7;
    font-weight: bold;
}

.money, .num {
    text-align: right;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
}

.negative {
    color: #9b2c2c;
}

.doc-header {
    border-bottom: 3px solid #1f3a68;
    padding-bottom: 8pt;
    margin-bottom: 14pt;
}

.doc-header .company {
    font-size: 14pt;
    font-weight: bold;
    color: #1f3a68;
    letter-spacing: 0.5pt;
}

.doc-header .title {
    font-size: 16pt;
    font-weight: bold;
    margin-top: 4pt;
}

.doc-header .meta {
    font-size: 9pt;
    color: #444;
    margin-top: 6pt;
}

.doc-header .meta span {
    display: inline-block;
    margin-right: 18pt;
}

.doc-footer {
    margin-top: 24pt;
    padding-top: 10pt;
    border-top: 1px solid #cfd8e8;
    font-size: 8.5pt;
    color: #555;
}

.confidential-notice {
    margin-top: 12pt;
    padding: 6pt 10pt;
    background-color: #fdf2f2;
    border: 1px solid #e3b4b4;
    color: #7a1f1f;
    font-size: 9pt;
}

.approval-block {
    margin-top: 20pt;
    display: flex;
    gap: 24pt;
}

.approval-block .sig-col {
    flex: 1;
    border-top: 1px solid #333;
    padding-top: 4pt;
    font-size: 9pt;
}

.approval-block .sig-col .label {
    font-weight: bold;
    display: block;
}

.section-attendance {
    margin: 6pt 0;
}

.section-attendance .attendee-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 4pt 14pt;
    font-size: 9.5pt;
}

ul, ol {
    margin: 4pt 0 6pt 20pt;
    padding: 0;
}

li {
    margin-bottom: 2pt;
}

p {
    margin: 3pt 0;
}

strong, b {
    font-weight: bold;
}

em, i {
    font-style: italic;
}

br {
    display: block;
    content: "";
    margin: 2pt 0;
}

@media print {
    .no-print {
        display: none !important;
    }
}
"""


def RENDER_PRINTABLE_CONTEXT(report=None) -> dict:
    return {
        "company": "MIMOM",
        "site": "Management Meeting Minutes Intranet",
        "generated_at": timezone.now(),
        "confidential_notice": (
            "CONFIDENTIAL — For authorized recipients only. "
            "Do not distribute or reproduce without written approval."
        ),
        "print_css": _PRINT_CSS,
        "report": report,
    }
