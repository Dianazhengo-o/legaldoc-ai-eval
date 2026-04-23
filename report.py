"""
從 eval JSON 產生視覺化 HTML 報告
"""

import html
import re
from collections import defaultdict
from pathlib import Path

STRATEGY_LABELS = {
    "plain_language": "白話版",
    "zero_shot": "Zero-Shot",
    "format_template": "格式模板",
    "few_shot": "Few-Shot",
    "chain_of_thought": "逐步推理",
}

EVIDENCE_ORDER = [
    "旅館住宿紀錄", "通訊軟體對話", "監視器畫面", "照片或影片",
    "目擊證人", "私家偵探報告", "GPS位置資料", "信用卡消費紀錄", "社群媒體貼文",
]


def decision_badge(decision: str) -> str:
    styles = {
        "是": ("badge-yes", "⚠️ 外遇成立"),
        "否": ("badge-no", "✅ 外遇不成立"),
        "不明": ("badge-unknown", "❓ 證據不明"),
    }
    cls, label = styles.get(decision, ("badge-unknown", "❓ 不明"))
    return f'<span class="{cls}">{label}</span>'


def parse_stars(text: str) -> int:
    m = re.search(r"(★+)", text)
    return len(m.group(1)) if m else 0


def render_stars(n: int) -> str:
    return (
        f'<span class="stars">'
        f'<span class="stars-filled">{"★" * n}</span>'
        f'<span class="stars-empty">{"☆" * (5 - n)}</span>'
        f'</span>'
    )


def render_plain_language(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"(★+☆*)", lambda m: render_stars(parse_stars(m.group(1))), text)
    text = re.sub(r"【(.+?)】", r'<h4 class="pl-heading">\1</h4>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace("\n", "<br>")
    return f'<div class="pl-box">{text}</div>'


def render_text(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"^(#{1,4})\s+(.+)$", lambda m: f"<strong>{m.group(2)}</strong>", text, flags=re.MULTILINE)
    text = text.replace("\n", "<br>")
    return text


def token_bar(value: int, max_value: int) -> str:
    pct = min(100, int(value / max_value * 100)) if max_value else 0
    return f'<div class="bar-wrap"><div class="bar" style="width:{pct}%"></div><span>{value:,}</span></div>'


def aggregate_evidence(all_results: list[dict]) -> dict:
    stats = defaultdict(lambda: {"count": 0, "yes": 0})
    for r in all_results:
        ev = r.get("evidence", {})
        decision = ev.get("decision", "不明")
        for etype in ev.get("evidence_types", []):
            stats[etype]["count"] += 1
            if decision == "是":
                stats[etype]["yes"] += 1
    return dict(stats)


def render_evidence_section(all_results: list[dict]) -> str:
    stats = aggregate_evidence(all_results)
    if not stats:
        return ""

    total = len(all_results)
    max_count = max(s["count"] for s in stats.values()) if stats else 1

    rows = ""
    for etype in EVIDENCE_ORDER:
        if etype not in stats:
            continue
        s = stats[etype]
        count = s["count"]
        yes = s["yes"]
        win_rate = yes / count if count else 0

        freq_pct = int(count / max_count * 100)
        win_color = "#16a34a" if win_rate >= 0.7 else "#ca8a04" if win_rate >= 0.4 else "#dc2626"

        rows += f"""
        <tr>
          <td class="ev-name">{etype}</td>
          <td>
            <div class="ev-bar-wrap">
              <div class="ev-bar" style="width:{freq_pct}%"></div>
              <span>{count} / {total} 份</span>
            </div>
          </td>
          <td>
            <div class="ev-bar-wrap">
              <div class="ev-bar" style="width:{int(win_rate*100)}%; background:{win_color}"></div>
              <span style="color:{win_color}; font-weight:600">{win_rate:.0%}</span>
            </div>
          </td>
          <td class="ev-count">{yes} 勝 / {count - yes} 敗</td>
        </tr>"""

    for etype in EVIDENCE_ORDER:
        if etype not in stats:
            rows += f"""
        <tr class="ev-absent">
          <td class="ev-name">{etype}</td>
          <td colspan="3" style="color:#cbd5e1; font-size:0.8rem">本批判決書未出現</td>
        </tr>"""

    return f"""
  <div class="section-title">證據要件有效性分析</div>
  <div class="evidence-note">根據本批 {total} 份判決書統計，哪種證據最容易讓法院認定外遇成立。</div>
  <table class="ev-table">
    <thead>
      <tr>
        <th>證據類型</th>
        <th>出現頻率</th>
        <th>外遇成立率</th>
        <th>勝敗統計</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>"""


def render_compensation_chart(all_results: list[dict]) -> str:
    data = []
    for r in all_results:
        ev = r.get("evidence", {})
        comp = ev.get("compensation", 0)
        decision = ev.get("decision", "不明")
        name = r["verdict"]
        short_name = name[:22] + "…" if len(name) > 22 else name
        data.append({"short": short_name, "full": name, "comp": comp, "decision": decision})

    data.sort(key=lambda x: x["comp"], reverse=True)
    max_comp = max((d["comp"] for d in data), default=1) or 1

    rows = ""
    for d in data:
        comp = d["comp"]
        decision = d["decision"]
        pct = int(comp / max_comp * 100) if comp else 0
        color = "#dc2626" if decision == "是" else "#16a34a" if decision == "否" else "#94a3b8"
        comp_str = f"NT$ {comp:,}" if comp else "無賠償"
        rows += f"""
        <tr>
          <td class="comp-name" title="{d['full']}">{d['short']}</td>
          <td class="comp-bar-cell">
            <div class="comp-bar-wrap">
              <div class="comp-bar" style="width:{pct}%; background:{color}"></div>
              <span class="comp-label" style="color:{color if comp else '#94a3b8'}">{comp_str}</span>
            </div>
          </td>
        </tr>"""

    return f"""
  <div class="section-title">損害賠償金額分布</div>
  <div class="evidence-note">各判決書賠償金額比較（由高到低排序）。紅色＝外遇成立，綠色＝外遇不成立，灰色＝不明。</div>
  <div class="comp-chart-wrap">
    <table class="comp-table">
      <tbody>{rows}</tbody>
    </table>
  </div>"""


def generate_html(all_results: list[dict], timestamp: str) -> str:
    all_tokens = [
        s["input_tokens"] + s["output_tokens"]
        for r in all_results for s in r["strategies"]
    ]
    max_tokens = max(all_tokens) if all_tokens else 1

    strategy_names = list(STRATEGY_LABELS.keys())
    strategy_stats = {}
    for name in strategy_names:
        rows = [s for r in all_results for s in r["strategies"] if s["strategy"] == name]
        if not rows:
            continue
        strategy_stats[name] = {
            "avg_in": sum(r["input_tokens"] for r in rows) / len(rows),
            "avg_out": sum(r["output_tokens"] for r in rows) / len(rows),
            "avg_sec": sum(r["elapsed_seconds"] for r in rows) / len(rows),
        }

    decisions = [r.get("evidence", {}).get("decision", "不明") for r in all_results]
    count_yes = decisions.count("是")
    count_no = decisions.count("否")
    count_unknown = decisions.count("不明")

    summary_rows = ""
    for r in all_results:
        ev = r.get("evidence", {})
        decision = ev.get("decision", "不明")
        compensation = ev.get("compensation", 0)
        comp_str = f"NT$ {compensation:,}" if compensation else "無"
        etypes = "、".join(ev.get("evidence_types", [])) or "—"
        badge = decision_badge(decision)
        name = r["verdict"]
        summary_rows += (
            f"<tr>"
            f"<td><a href='#{name}'>{name}</a></td>"
            f"<td>{badge}</td>"
            f"<td>{comp_str}</td>"
            f"<td class='ev-tags'>{etypes}</td>"
            f"</tr>"
        )

    stat_rows = ""
    for name in strategy_names:
        if name not in strategy_stats:
            continue
        st = strategy_stats[name]
        label = STRATEGY_LABELS[name]
        total_avg = st["avg_in"] + st["avg_out"]
        bar_pct = int(total_avg / (max(s["avg_in"] + s["avg_out"] for s in strategy_stats.values())) * 100)
        stat_rows += f"""
        <tr>
          <td>{label}</td>
          <td>{st['avg_in']:.0f}</td>
          <td>{st['avg_out']:.0f}</td>
          <td>
            <div class="bar-wrap">
              <div class="bar" style="width:{bar_pct}%"></div>
              <span>{total_avg:.0f}</span>
            </div>
          </td>
          <td>{st['avg_sec']:.1f}s</td>
        </tr>"""

    verdict_sections = ""
    for r in all_results:
        name = r["verdict"]
        ev = r.get("evidence", {})
        decision = ev.get("decision", "不明")
        compensation = ev.get("compensation", 0)
        comp_str = f"NT$ {compensation:,}" if compensation else "無賠償"
        etypes = ev.get("evidence_types", [])
        badge = decision_badge(decision)

        etags = "".join(f'<span class="etag">{t}</span>' for t in etypes) or '<span class="etag etag-none">無明確事證</span>'

        tabs_nav = ""
        tabs_content = ""
        for i, s in enumerate(r["strategies"]):
            sname = s["strategy"]
            label = STRATEGY_LABELS.get(sname, sname)
            active = "active" if i == 0 else ""
            is_plain = sname == "plain_language"
            tab_extra = ' tab-plain' if is_plain else ''
            tabs_nav += f'<button class="tab-btn {active}{tab_extra}" onclick="showTab(this,\'{name}-{sname}\')">{label}</button>'

            total_tok = s["input_tokens"] + s["output_tokens"]
            content_html = render_plain_language(s["output"]) if is_plain else f'<div class="output-box">{render_text(s["output"])}</div>'

            tabs_content += f"""
            <div id="{name}-{sname}" class="tab-pane {active}">
              <div class="token-row">
                <div class="token-item"><label>輸入 tokens</label>{token_bar(s['input_tokens'], max_tokens)}</div>
                <div class="token-item"><label>輸出 tokens</label>{token_bar(s['output_tokens'], max_tokens)}</div>
                <div class="token-meta">耗時 {s['elapsed_seconds']}s　共 {total_tok:,} tokens</div>
              </div>
              {content_html}
            </div>"""

        verdict_sections += f"""
        <section class="verdict-card" id="{name}" data-decision="{decision}">
          <div class="verdict-header">
            <div class="verdict-title">
              <h2>{name}</h2>
              <div class="etags">{etags}</div>
            </div>
            <div class="verdict-meta">
              {badge}
              <span class="compensation">{comp_str}</span>
            </div>
          </div>
          <div class="tabs-nav">{tabs_nav}</div>
          <div class="tabs-body">{tabs_content}</div>
        </section>"""

    evidence_section = render_evidence_section(all_results)
    compensation_chart = render_compensation_chart(all_results)

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>外遇判決書 AI Eval 報告</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Noto Sans TC","Microsoft JhengHei",sans-serif; background:#f5f5f5; color:#333; }}
  a {{ color:#2563eb; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}

  .page-header {{ background:#1e293b; color:#fff; padding:32px 40px; }}
  .page-header h1 {{ font-size:1.6rem; margin-bottom:4px; }}
  .page-header .subtitle {{ color:#94a3b8; font-size:0.9rem; }}

  .container {{ max-width:1100px; margin:0 auto; padding:32px 20px; }}

  .stats-row {{ display:flex; gap:16px; margin-bottom:32px; flex-wrap:wrap; }}
  .stat-card {{ background:#fff; border-radius:10px; padding:20px 28px; flex:1; min-width:130px;
                box-shadow:0 1px 4px rgba(0,0,0,.08); text-align:center; }}
  .stat-card .num {{ font-size:2.2rem; font-weight:700; line-height:1; }}
  .stat-card .lbl {{ font-size:0.82rem; color:#64748b; margin-top:4px; }}
  .num-yes {{ color:#dc2626; }} .num-no {{ color:#16a34a; }}
  .num-unk {{ color:#ca8a04; }} .num-tot {{ color:#2563eb; }}

  .section-title {{ font-size:1.05rem; font-weight:700; margin-bottom:8px; color:#1e293b; }}

  /* 總覽表 */
  .summary-table {{ width:100%; background:#fff; border-radius:10px;
    box-shadow:0 1px 4px rgba(0,0,0,.08); border-collapse:collapse; overflow:hidden; margin-bottom:40px; }}
  .summary-table th {{ background:#1e293b; color:#fff; padding:10px 16px; text-align:left; font-size:0.85rem; }}
  .summary-table td {{ padding:10px 16px; border-bottom:1px solid #f1f5f9; font-size:0.85rem; vertical-align:middle; }}
  .summary-table tr:last-child td {{ border-bottom:none; }}
  .summary-table tr:hover td {{ background:#f8fafc; }}
  .ev-tags {{ color:#475569; font-size:0.78rem; }}

  /* 策略統計表 */
  .stat-table {{ width:100%; background:#fff; border-radius:10px;
    box-shadow:0 1px 4px rgba(0,0,0,.08); border-collapse:collapse; overflow:hidden; margin-bottom:40px; }}
  .stat-table th {{ background:#334155; color:#fff; padding:10px 16px; font-size:0.85rem; text-align:right; }}
  .stat-table th:first-child {{ text-align:left; }}
  .stat-table td {{ padding:10px 16px; border-bottom:1px solid #f1f5f9; font-size:0.85rem; text-align:right; }}
  .stat-table td:first-child {{ text-align:left; font-weight:600; }}
  .stat-table tr:last-child td {{ border-bottom:none; }}

  /* Badge */
  .badge-yes     {{ background:#fee2e2; color:#b91c1c; padding:3px 12px; border-radius:20px; font-size:0.82rem; font-weight:600; white-space:nowrap; }}
  .badge-no      {{ background:#dcfce7; color:#15803d; padding:3px 12px; border-radius:20px; font-size:0.82rem; font-weight:600; white-space:nowrap; }}
  .badge-unknown {{ background:#fef9c3; color:#a16207; padding:3px 12px; border-radius:20px; font-size:0.82rem; font-weight:600; white-space:nowrap; }}

  /* 證據要件 */
  .evidence-note {{ font-size:0.82rem; color:#64748b; margin-bottom:12px; }}
  .ev-table {{ width:100%; background:#fff; border-radius:10px;
    box-shadow:0 1px 4px rgba(0,0,0,.08); border-collapse:collapse; overflow:hidden; margin-bottom:40px; }}
  .ev-table th {{ background:#0f172a; color:#fff; padding:10px 16px; text-align:left; font-size:0.82rem; }}
  .ev-table td {{ padding:10px 16px; border-bottom:1px solid #f1f5f9; font-size:0.85rem; vertical-align:middle; }}
  .ev-table tr:last-child td {{ border-bottom:none; }}
  .ev-table tr:hover td {{ background:#f8fafc; }}
  .ev-absent td {{ opacity:0.45; }}
  .ev-name {{ font-weight:600; white-space:nowrap; }}
  .ev-count {{ color:#64748b; font-size:0.8rem; white-space:nowrap; }}
  .ev-bar-wrap {{ display:flex; align-items:center; gap:10px; }}
  .ev-bar {{ height:10px; border-radius:5px; background:#3b82f6; min-width:4px; }}

  /* 賠償金額圖 */
  .comp-chart-wrap {{ background:#fff; border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,.08);
    padding:16px 20px; margin-bottom:40px; }}
  .comp-table {{ width:100%; border-collapse:collapse; }}
  .comp-table td {{ padding:6px 8px; vertical-align:middle; }}
  .comp-name {{ font-size:0.8rem; color:#475569; white-space:nowrap; width:200px; max-width:200px;
    overflow:hidden; text-overflow:ellipsis; }}
  .comp-bar-cell {{ width:100%; }}
  .comp-bar-wrap {{ display:flex; align-items:center; gap:10px; }}
  .comp-bar {{ height:18px; border-radius:4px; min-width:4px; transition:width .3s; }}
  .comp-label {{ font-size:0.8rem; font-weight:600; white-space:nowrap; }}

  /* 篩選按鈕 */
  .filter-row {{ display:flex; align-items:center; gap:8px; margin-bottom:16px; flex-wrap:wrap; }}
  .filter-label {{ font-size:0.85rem; color:#64748b; font-weight:600; }}
  .filter-btn {{ padding:6px 16px; border-radius:20px; border:2px solid #e2e8f0; background:#fff;
    cursor:pointer; font-size:0.82rem; font-family:inherit; color:#64748b; transition:all .15s; }}
  .filter-btn:hover {{ border-color:#94a3b8; color:#1e293b; }}
  .filter-btn.active {{ background:#1e293b; color:#fff; border-color:#1e293b; }}
  .filter-btn.btn-yes.active {{ background:#dc2626; border-color:#dc2626; }}
  .filter-btn.btn-no.active {{ background:#16a34a; border-color:#16a34a; }}
  .filter-btn.btn-unk.active {{ background:#ca8a04; border-color:#ca8a04; }}
  .filter-count {{ font-size:0.75rem; opacity:0.75; margin-left:2px; }}

  /* 判決書卡片 */
  .verdict-card {{ background:#fff; border-radius:12px; box-shadow:0 1px 6px rgba(0,0,0,.1);
    margin-bottom:28px; overflow:hidden; }}
  .verdict-header {{ display:flex; justify-content:space-between; align-items:flex-start;
    padding:20px 24px; border-bottom:1px solid #f1f5f9; flex-wrap:wrap; gap:12px; }}
  .verdict-title h2 {{ font-size:0.95rem; color:#1e293b; margin-bottom:6px; word-break:break-all; }}
  .etags {{ display:flex; flex-wrap:wrap; gap:4px; }}
  .etag {{ background:#eff6ff; color:#1d4ed8; padding:2px 8px; border-radius:12px; font-size:0.75rem; }}
  .etag-none {{ background:#f1f5f9; color:#94a3b8; }}
  .verdict-meta {{ display:flex; flex-direction:column; align-items:flex-end; gap:6px; }}
  .compensation {{ font-size:0.82rem; color:#475569; font-weight:600; }}

  /* Tabs */
  .tabs-nav {{ display:flex; background:#f8fafc; border-bottom:1px solid #e2e8f0; overflow-x:auto; }}
  .tab-btn {{ flex:1; min-width:80px; padding:10px 8px; border:none; background:transparent; cursor:pointer;
    font-size:0.82rem; color:#64748b; font-family:inherit; white-space:nowrap; transition:all .15s; }}
  .tab-btn:hover {{ background:#e2e8f0; color:#1e293b; }}
  .tab-btn.active {{ background:#fff; color:#2563eb; font-weight:700; border-bottom:2px solid #2563eb; margin-bottom:-1px; }}
  .tab-btn.tab-plain.active {{ color:#7c3aed; border-bottom-color:#7c3aed; }}
  .tab-pane {{ display:none; padding:20px 24px; }}
  .tab-pane.active {{ display:block; }}

  /* Token bar */
  .token-row {{ display:flex; gap:20px; flex-wrap:wrap; align-items:center;
    background:#f8fafc; border-radius:8px; padding:12px 16px; margin-bottom:16px; }}
  .token-item {{ flex:1; min-width:150px; }}
  .token-item label {{ font-size:0.75rem; color:#64748b; display:block; margin-bottom:4px; }}
  .bar-wrap {{ display:flex; align-items:center; gap:8px; }}
  .bar {{ height:8px; border-radius:4px; background:#3b82f6; min-width:4px; }}
  .bar-wrap span {{ font-size:0.8rem; color:#475569; white-space:nowrap; }}
  .token-meta {{ font-size:0.78rem; color:#94a3b8; white-space:nowrap; }}

  /* 白話版 */
  .pl-box {{ font-size:0.92rem; line-height:1.9; color:#1e293b; }}
  .pl-heading {{ font-size:0.82rem; font-weight:700; color:#7c3aed; margin:14px 0 4px;
    text-transform:uppercase; letter-spacing:.05em; }}
  .stars {{ font-size:1.3rem; }}
  .stars-filled {{ color:#f59e0b; }}
  .stars-empty {{ color:#d1d5db; }}

  /* 一般輸出 */
  .output-box {{ font-size:0.88rem; line-height:1.8; color:#374151;
    border-left:3px solid #e2e8f0; padding-left:16px; }}

  .no-results {{ text-align:center; padding:40px; color:#94a3b8; font-size:0.9rem; display:none; }}
</style>
</head>
<body>

<div class="page-header">
  <h1>外遇判決書 AI Eval 報告</h1>
  <div class="subtitle">執行時間：{timestamp}　｜　模型：gpt-4o-mini　｜　策略數：{len(STRATEGY_LABELS)}</div>
</div>

<div class="container">

  <div class="stats-row">
    <div class="stat-card"><div class="num num-tot">{len(all_results)}</div><div class="lbl">判決書總數</div></div>
    <div class="stat-card"><div class="num num-yes">{count_yes}</div><div class="lbl">外遇成立</div></div>
    <div class="stat-card"><div class="num num-no">{count_no}</div><div class="lbl">外遇不成立</div></div>
    <div class="stat-card"><div class="num num-unk">{count_unknown}</div><div class="lbl">證據不明</div></div>
  </div>

  <div class="section-title">判決結果一覽</div>
  <table class="summary-table">
    <thead><tr><th>判決書</th><th>外遇認定</th><th>損害賠償</th><th>主要事證</th></tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>

  {evidence_section}

  {compensation_chart}

  <div class="section-title">策略效能比較（平均 token 使用量）</div>
  <table class="stat-table">
    <thead><tr><th>策略</th><th>平均輸入</th><th>平均輸出</th><th>合計（視覺化）</th><th>平均耗時</th></tr></thead>
    <tbody>{stat_rows}</tbody>
  </table>

  <div class="section-title">各判決書詳細分析</div>
  <div class="filter-row">
    <span class="filter-label">篩選：</span>
    <button class="filter-btn active" onclick="filterVerdicts('all', this)">全部 <span class="filter-count">({len(all_results)})</span></button>
    <button class="filter-btn btn-yes" onclick="filterVerdicts('是', this)">外遇成立 <span class="filter-count">({count_yes})</span></button>
    <button class="filter-btn btn-no" onclick="filterVerdicts('否', this)">外遇不成立 <span class="filter-count">({count_no})</span></button>
    <button class="filter-btn btn-unk" onclick="filterVerdicts('不明', this)">證據不明 <span class="filter-count">({count_unknown})</span></button>
  </div>
  <div id="no-results" class="no-results">沒有符合篩選條件的判決書</div>
  {verdict_sections}

</div>

<script>
function showTab(btn, tabId) {{
  const card = btn.closest('.verdict-card');
  card.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  card.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(tabId).classList.add('active');
}}

function filterVerdicts(decision, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const cards = document.querySelectorAll('.verdict-card');
  let visible = 0;
  cards.forEach(card => {{
    const show = decision === 'all' || card.dataset.decision === decision;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('no-results').style.display = visible === 0 ? 'block' : 'none';
}}
</script>
</body>
</html>"""


def save_html(all_results: list[dict], timestamp: str, results_dir: Path) -> Path:
    html = generate_html(all_results, timestamp)
    path = results_dir / f"外遇分析報告_{timestamp}.html"
    path.write_text(html, encoding="utf-8")
    return path
