#!/usr/bin/env python3
"""
Generate printable PDF manuals from the architecture markdown documentation
in poor-mans-defense-lakehouse/docs/architecture.

Features:
- Renders all Mermaid diagrams client-side using Mermaid.js and captures crisp vector SVGs
- Styles code snippets with Pygments syntax highlighting
- Print-optimized CSS (page breaks, margins, typography, high contrast)
- Generates a Unified Master Architecture Manual (with Cover, TOC, 7 Chapters, and Appendix)
- Generates Individual Standalone PDFs for each architecture topic
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path

# External dependencies handled via uv or system python
import markdown
import pygments
from pygments.formatters import HtmlFormatter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs" / "architecture"
OUTPUT_DIR = DOCS_DIR / "pdf"
INDIVIDUAL_DIR = OUTPUT_DIR / "individual"
ASSETS_DIR = DOCS_DIR / "pdf_assets"
MERMAID_JS_PATH = ASSETS_DIR / "mermaid.min.js"
VERSION_FILE = PROJECT_ROOT / "VERSION"
RENDERER_JS = PROJECT_ROOT / "tools" / "pdf_renderer.js"

# Read version
if VERSION_FILE.exists():
    VERSION = VERSION_FILE.read_text().strip()
else:
    VERSION = "0.1.0"

# Architecture document order and metadata
CHAPTERS = [
    {
        "id": "ch1",
        "file": "microservice_domain_architecture.md",
        "title": "Microservice Domain Architecture Guide",
        "number": "Chapter 1",
        "desc": "Hexagonal domain organization, 8 core domains, 34 REST API endpoints, Zero-Trust RBAC security."
    },
    {
        "id": "ch2",
        "file": "clean_architecture_and_testing.md",
        "title": "Clean Production Architecture & Decoupled Test Harness",
        "number": "Chapter 2",
        "desc": "Zero mocks in production, typed domain exceptions, and offline test doubles architecture."
    },
    {
        "id": "ch3",
        "file": "data_ingestion_guide.md",
        "title": "Data Ingestion Architecture & Operations Guide",
        "number": "Chapter 3",
        "desc": "High-frequency telemetry ingestion via Kafka, Temporal workflows, and Bronze/Silver/Gold storage."
    },
    {
        "id": "ch4",
        "file": "project_data_pipelines.md",
        "title": "Project Data Pipelines & Sandboxed Medallion Execution",
        "number": "Chapter 4",
        "desc": "Project workspace isolation, AST script security validation, ephemeral Docker sandboxing, and DuckDB queries."
    },
    {
        "id": "ch5",
        "file": "knowledge_discovery_graph_guide.md",
        "title": "Universal Domain-Agnostic Knowledge Discovery Graph (KDG)",
        "number": "Chapter 5",
        "desc": "Memgraph graph ontology, multi-tenant workspace isolation, and two-phase entity resolution pipeline."
    },
    {
        "id": "ch6",
        "file": "ai_rag_scenario.md",
        "title": "End-to-End Scenario Flow: artemis ask (AI RAG)",
        "number": "Chapter 6",
        "desc": "Multi-agent autonomous RAG loop, Google AI Studio integration, guardian critic, and read-only AST guardrails."
    },
    {
        "id": "ch7",
        "file": "google_ai_studio_integration.md",
        "title": "Google AI Studio Integration & Fail-Fast Architecture",
        "number": "Chapter 7",
        "desc": "Cloud LLM integration rationale, function call tool contracts, API key security, and offline mock fallbacks."
    },
    {
        "id": "app_ideas",
        "file": "ideas/knowledge_discovery_graph.md",
        "title": "Appendix: Knowledge Discovery Graph Conceptual Notes",
        "number": "Appendix A",
        "desc": "Exploratory design specifications, node schemas, and architectural inception notes."
    }
]

# Generate Pygments CSS for light theme
pygments_css = HtmlFormatter(style="friendly").get_style_defs(".codehilite")

BASE_CSS = f"""
@charset "utf-8";

/* Page Setup */
@page {{
    size: A4 portrait;
    margin: 18mm 16mm 20mm 16mm;
}}

* {{
    box-sizing: border-box;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #0f172a;
    background-color: #ffffff;
    line-height: 1.55;
    font-size: 10pt;
    margin: 0;
    padding: 0;
}}

/* Typography */
h1, h2, h3, h4, h5, h6 {{
    color: #0f172a;
    font-weight: 700;
    line-height: 1.25;
    margin-top: 1.4em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
    break-after: avoid;
}}

h1 {{
    font-size: 19pt;
    border-bottom: 2px solid #0284c7;
    padding-bottom: 6px;
    margin-top: 0;
}}

.chapter-heading {{
    page-break-before: always;
    break-before: always;
    padding-top: 10px;
}}

.chapter-number {{
    display: inline-block;
    font-size: 9pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #0284c7;
    background: #e0f2fe;
    padding: 3px 8px;
    border-radius: 4px;
    margin-bottom: 8px;
}}

h2 {{
    font-size: 14pt;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin-top: 1.6em;
}}

h3 {{
    font-size: 11.5pt;
    color: #1e293b;
    margin-top: 1.3em;
}}

h4 {{
    font-size: 10.5pt;
    color: #334155;
}}

p, ul, ol {{
    margin-top: 0.5em;
    margin-bottom: 0.7em;
}}

ul, ol {{
    padding-left: 1.5em;
}}

li {{
    margin-bottom: 0.25em;
}}

a {{
    color: #0284c7;
    text-decoration: none;
}}

hr {{
    border: none;
    border-top: 1px solid #cbd5e1;
    margin: 1.8em 0;
}}

/* Blockquotes / Callouts */
blockquote {{
    border-left: 4px solid #0284c7;
    background-color: #f0f9ff;
    color: #0369a1;
    margin: 1em 0;
    padding: 0.6em 1em;
    border-radius: 0 4px 4px 0;
    page-break-inside: avoid;
    break-inside: avoid;
}}

blockquote p {{
    margin: 0;
}}

/* Tables */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1.2em 0;
    font-size: 9pt;
    page-break-inside: avoid;
    break-inside: avoid;
}}

th, td {{
    border: 1px solid #cbd5e1;
    padding: 6px 10px;
    text-align: left;
    vertical-align: top;
}}

th {{
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 600;
}}

tr:nth-child(even) td {{
    background-color: #f8fafc;
}}

/* Code Blocks & Inline Code */
code {{
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
    font-size: 8.5pt;
    background-color: #f1f5f9;
    color: #0f172a;
    padding: 1.5px 4px;
    border-radius: 3px;
    border: 1px solid #e2e8f0;
}}

pre {{
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
    font-size: 8pt;
    line-height: 1.45;
    background-color: #f8fafc;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 10px 12px;
    overflow-x: auto;
    page-break-inside: avoid;
    break-inside: avoid;
    margin: 1em 0;
}}

pre code {{
    background-color: transparent;
    padding: 0;
    border: none;
    font-size: inherit;
    color: inherit;
}}

/* Pygments Syntax Highlighting */
{pygments_css}

/* Mermaid Diagrams Container */
.mermaid-container {{
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    margin: 1.6em 0;
    padding: 16px 12px;
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}

.mermaid-container svg {{
    max-width: 100% !important;
    height: auto !important;
    display: inline-block;
    margin: 0 auto;
}}

.diagram-caption {{
    margin-top: 8px;
    font-size: 8pt;
    color: #64748b;
    font-style: italic;
}}

/* Cover Page */
.cover-page {{
    page-break-after: always;
    break-after: always;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 860px;
    padding: 40px 20px 20px 20px;
}}

.cover-header {{
    border-bottom: 4px solid #0284c7;
    padding-bottom: 25px;
}}

.cover-badge {{
    display: inline-block;
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #ffffff;
    background: #0284c7;
    padding: 4px 10px;
    border-radius: 4px;
    margin-bottom: 18px;
}}

.cover-title {{
    font-size: 32pt;
    font-weight: 800;
    color: #0f172a;
    line-height: 1.15;
    margin: 0 0 12px 0;
    border: none;
    padding: 0;
}}

.cover-subtitle {{
    font-size: 15pt;
    font-weight: 500;
    color: #475569;
    line-height: 1.4;
    margin: 0;
}}

.cover-overview {{
    margin: 35px 0;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 24px;
}}

.cover-overview h3 {{
    margin-top: 0;
    font-size: 11pt;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #0284c7;
}}

.cover-pillars {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-top: 15px;
}}

.pillar-item {{
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 8.5pt;
}}

.pillar-item strong {{
    display: block;
    color: #0f172a;
    font-size: 9pt;
    margin-bottom: 2px;
}}

.cover-footer {{
    border-top: 1px solid #cbd5e1;
    padding-top: 16px;
    font-size: 8.5pt;
    color: #64748b;
    display: flex;
    justify-content: space-between;
}}

/* Table of Contents Page */
.toc-page {{
    page-break-after: always;
    break-after: always;
    padding-top: 15px;
}}

.toc-title {{
    font-size: 18pt;
    border-bottom: 2px solid #0284c7;
    padding-bottom: 6px;
    margin-bottom: 20px;
}}

.toc-list {{
    list-style: none;
    padding: 0;
    margin: 0;
}}

.toc-item {{
    margin-bottom: 14px;
    padding-bottom: 12px;
    border-bottom: 1px dashed #e2e8f0;
}}

.toc-item-header {{
    display: flex;
    justify-content: space-between;
    font-size: 11pt;
    font-weight: 600;
}}

.toc-item-number {{
    color: #0284c7;
    margin-right: 8px;
}}

.toc-item-title {{
    color: #0f172a;
}}

.toc-item-desc {{
    font-size: 8.5pt;
    color: #64748b;
    margin-top: 3px;
    padding-left: 2px;
}}
"""

def extract_and_convert_markdown(md_text, chapter_info=None):
    """
    Extracts mermaid code blocks, replaces with placeholders,
    converts markdown to HTML, then replaces placeholders with mermaid divs.
    """
    placeholders = {}
    
    def mermaid_repl(m):
        idx = len(placeholders)
        code = m.group(1).strip()
        # Ensure any syntax issues (like participant Loop) are sanitized
        code = re.sub(r'\bparticipant Loop\b', 'participant AgentLoop', code)
        code = re.sub(r'->Loop:', '->AgentLoop:', code)
        code = re.sub(r'-->>Loop:', '-->>AgentLoop:', code)
        code = re.sub(r'Loop->>', 'AgentLoop->>', code)
        code = re.sub(r'Loop-->>', 'AgentLoop-->>', code)
        key = f"<!--MERMAID_PLACEHOLDER_{idx}-->"
        placeholders[key] = code
        return f"\n\n{key}\n\n"

    clean_md = re.sub(r"```mermaid\s*\n(.*?)\n```", mermaid_repl, md_text, flags=re.DOTALL)

    # Convert markdown to HTML
    html = markdown.markdown(
        clean_md,
        extensions=[
            "fenced_code",
            "tables",
            "toc",
            "codehilite",
            "sane_lists",
            "attr_list"
        ],
        extension_configs={
            "codehilite": {
                "css_class": "codehilite",
                "guess_lang": False,
                "use_pygments": True
            }
        }
    )

    # Re-insert Mermaid containers
    for key, code in placeholders.items():
        escaped_code = (code.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;"))
        container = (
            f'<div class="mermaid-container">\n'
            f'<pre class="mermaid">{escaped_code}</pre>\n'
            f'</div>'
        )
        html = html.replace(key, container)

    return html, len(placeholders)


def create_full_html_document(body_content, title="Poor Man's Defense Lakehouse - Architecture"):
    """Wraps body HTML in a complete document with Mermaid.js embedded."""
    mermaid_js = MERMAID_JS_PATH.read_text(encoding="utf-8")
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
{BASE_CSS}
</style>
<script>
{mermaid_js}
</script>
</head>
<body>
{body_content}
<script>
(function() {{
    window.__READY__ = false;
    window.__DIAGRAM_COUNT__ = 0;
    window.__RENDER_ERRORS__ = 0;

    mermaid.initialize({{
        startOnLoad: false,
        theme: 'default',
        securityLevel: 'loose',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        themeVariables: {{
            fontSize: '12px',
            primaryColor: '#e0f2fe',
            primaryTextColor: '#0f172a',
            primaryBorderColor: '#0284c7',
            lineColor: '#334155',
            secondaryColor: '#f8fafc',
            tertiaryColor: '#ffffff'
        }},
        flowchart: {{
            useMaxWidth: true,
            htmlLabels: true,
            curve: 'basis'
        }},
        sequence: {{
            useMaxWidth: true,
            diagramMarginX: 10,
            diagramMarginY: 10,
            actorMargin: 35,
            boxMargin: 8,
            boxTextMargin: 5,
            noteMargin: 8,
            messageMargin: 25
        }}
    }});

    async function renderDiagrams() {{
        const nodes = document.querySelectorAll('.mermaid');
        window.__DIAGRAM_COUNT__ = nodes.length;
        let errors = 0;

        for (let i = 0; i < nodes.length; i++) {{
            const el = nodes[i];
            const code = el.textContent.trim();

            try {{
                const id = 'mermaid-render-' + i;
                const res = await mermaid.render(id, code);
                el.innerHTML = res.svg;
            }} catch (err) {{
                errors++;
                console.error('Error rendering diagram #' + i, err);
                el.innerHTML = '<div style="color:#b91c1c; font-size:9pt; background:#fef2f2; border:1px solid #f87171; padding:10px; text-align:left; border-radius:4px;"><strong>Diagram Render Error:</strong> ' + err.message + '<pre style="margin-top:6px; font-size:7.5pt;">' + code + '</pre></div>';
            }}
        }}

        window.__RENDER_ERRORS__ = errors;
        window.__READY__ = true;
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', renderDiagrams);
    }} else {{
        renderDiagrams();
    }}
}})();
</script>
</body>
</html>
"""


def generate_master_manual():
    print("\n=======================================================")
    print("Building Master Architecture Reference Manual")
    print("=======================================================")

    # 1. Cover Page
    cover_html = f"""
    <div class="cover-page">
        <div class="cover-header">
            <div class="cover-badge">System Architecture Specification • Version {VERSION}</div>
            <h1 class="cover-title">Poor Man's Defense Lakehouse</h1>
            <p class="cover-subtitle">Autonomous Intelligence, Sandboxed Pipelines & Knowledge Graph Architecture Reference Manual</p>
        </div>

        <div class="cover-overview">
            <h3>Architecture Foundation & Core Pillars</h3>
            <p style="font-size: 9.5pt; color: #334155; margin-bottom: 12px;">
                Poor Man's Defense Lakehouse is a sovereign, zero-JVM, high-performance data intelligence platform inspired by the French defense ARTEMIS.IA initiative. It unifies telemetry ingestion, graph ontology, sandboxed pipelines, and autonomous AI reasoning.
            </p>
            <div class="cover-pillars">
                <div class="pillar-item">
                    <strong>1. Hexagonal Domain Organization</strong>
                    8 isolated domains, decoupled repository interfaces, and strict zero-trust context variables.
                </div>
                <div class="pillar-item">
                    <strong>2. Zero-Mock Production Guarantees</strong>
                    100% clean production code without test mock remnants; decoupled reusable test doubles.
                </div>
                <div class="pillar-item">
                    <strong>3. Scalable Telemetry Ingestion</strong>
                    Kafka ingestion buffer, Temporal durable workflows, and S3 Parquet Bronze/Silver/Gold tiers.
                </div>
                <div class="pillar-item">
                    <strong>4. Secure Project Isolation</strong>
                    Tenant workspace boundaries, AST script validation, and ephemeral Docker sandbox runners.
                </div>
                <div class="pillar-item">
                    <strong>5. Knowledge Discovery Graph (KDG)</strong>
                    Memgraph openCypher graph ontology with automated cross-project entity resolution.
                </div>
                <div class="pillar-item">
                    <strong>6. Grounded Multi-Agent RAG</strong>
                    Google AI Studio Gemini function calling with read-only AST guardrails and guardian critic.
                </div>
            </div>
        </div>

        <div class="cover-footer">
            <span><strong>Target Audience:</strong> Architecture Review Board & Engineering Teams</span>
            <span><strong>Date:</strong> October 2026</span>
            <span><strong>Edition:</strong> High-Resolution Print Ready</span>
        </div>
    </div>
    """

    # 2. Table of Contents
    toc_items = []
    for ch in CHAPTERS:
        toc_items.append(f"""
        <li class="toc-item">
            <div class="toc-item-header">
                <span><span class="toc-item-number">{ch['number']}</span><span class="toc-item-title">{ch['title']}</span></span>
            </div>
            <div class="toc-item-desc">{ch['desc']}</div>
        </li>
        """)

    toc_html = f"""
    <div class="toc-page">
        <h2 class="toc-title">Table of Contents</h2>
        <ul class="toc-list">
            {''.join(toc_items)}
        </ul>
    </div>
    """

    # 3. Chapters
    chapters_html = []
    total_diagrams = 0

    for ch in CHAPTERS:
        file_path = DOCS_DIR / ch["file"]
        if not file_path.exists():
            print(f"Warning: File not found: {file_path}")
            continue

        raw_md = file_path.read_text(encoding="utf-8")
        ch_html, diag_count = extract_and_convert_markdown(raw_md, ch)
        total_diagrams += diag_count

        # Wrap chapter in section
        section = f"""
        <section id="{ch['id']}" class="chapter-heading">
            <div class="chapter-number">{ch['number']}</div>
            {ch_html}
        </section>
        """
        chapters_html.append(section)

    full_body = cover_html + toc_html + "\n".join(chapters_html)
    full_html = create_full_html_document(full_body, "Poor Man's Defense Lakehouse - Architecture Reference Manual")

    temp_html_path = OUTPUT_DIR / "master_manual.html"
    master_pdf_path = OUTPUT_DIR / "Artemis_IA_Architecture_Manual.pdf"
    symlink_pdf_path = DOCS_DIR / "Artemis_IA_Architecture_Manual.pdf"

    temp_html_path.write_text(full_html, encoding="utf-8")
    print(f"Generated intermediate HTML: {temp_html_path} ({len(full_html) // 1024} KB, {total_diagrams} diagrams)")

    # Call renderer
    subprocess.run([
        "node",
        str(RENDERER_JS),
        str(temp_html_path),
        str(master_pdf_path),
        "Architecture Reference Manual"
    ], check=True)

    # Create root docs symlink/copy for convenient access
    if master_pdf_path.exists():
        import shutil
        shutil.copyfile(master_pdf_path, symlink_pdf_path)
        print(f"Copied primary master PDF to: {symlink_pdf_path}")

    # Clean intermediate HTML
    if temp_html_path.exists():
        temp_html_path.unlink()

    return master_pdf_path


def generate_individual_pdfs():
    print("\n=======================================================")
    print("Building Individual Standalone Architecture PDFs")
    print("=======================================================")
    INDIVIDUAL_DIR.mkdir(parents=True, exist_ok=True)

    generated = []
    for idx, ch in enumerate(CHAPTERS, 1):
        file_path = DOCS_DIR / ch["file"]
        if not file_path.exists():
            continue

        base_name = file_path.stem
        pdf_name = f"{idx:02d}_{base_name}.pdf"
        pdf_path = INDIVIDUAL_DIR / pdf_name
        temp_html_path = INDIVIDUAL_DIR / f"{base_name}.html"

        raw_md = file_path.read_text(encoding="utf-8")
        ch_html, diag_count = extract_and_convert_markdown(raw_md, ch)

        body = f"""
        <div style="margin-bottom: 25px; padding-bottom: 15px; border-bottom: 2px solid #0284c7;">
            <div class="chapter-number">{ch['number']} • Poor Man's Defense Lakehouse</div>
            <div style="font-size: 8.5pt; color: #64748b; margin-top: 5px;">Single Topic Print Edition • Version {VERSION}</div>
        </div>
        {ch_html}
        """

        full_html = create_full_html_document(body, f"{ch['title']} - Poor Man's Defense Lakehouse")
        temp_html_path.write_text(full_html, encoding="utf-8")

        subprocess.run([
            "node",
            str(RENDERER_JS),
            str(temp_html_path),
            str(pdf_path),
            ch["title"]
        ], check=True)

        if temp_html_path.exists():
            temp_html_path.unlink()

        generated.append(pdf_path)

    return generated


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    master_pdf = generate_master_manual()
    individual_pdfs = generate_individual_pdfs()

    print("\n=======================================================")
    print("SUCCESS: Architecture PDFs Successfully Generated!")
    print("=======================================================")
    print(f"Master Manual: {master_pdf}")
    print(f"Individual PDFs ({len(individual_pdfs)} files) in: {INDIVIDUAL_DIR}")
    for p in individual_pdfs:
        stat = p.stat()
        print(f"  - {p.name} ({(stat.st_size/1024):.1f} KB)")


if __name__ == "__main__":
    main()
