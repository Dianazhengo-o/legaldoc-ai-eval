"""
台灣法院外遇判決書 AI Eval
執行 5 種 prompt 策略並輸出比較結果
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path

import re
import openai
import fitz  # pymupdf
from dotenv import load_dotenv
from prompts import STRATEGIES, SYSTEM_PROMPT, evidence_extraction
from report import save_html

load_dotenv()

MODEL = "gpt-4o-mini"
BASE_DIR = Path(__file__).parent
VERDICTS_DIR = BASE_DIR / "verdicts"
RESULTS_DIR = BASE_DIR / "results"


def extract_pdf(path: Path) -> str:
    with fitz.open(path) as doc:
        return "".join(page.get_text() for page in doc)


def load_verdicts() -> dict[str, str]:
    verdicts = {}
    for path in sorted(VERDICTS_DIR.glob("*.txt")):
        verdicts[path.stem] = path.read_text(encoding="utf-8")
    for path in sorted(VERDICTS_DIR.glob("*.pdf")):
        text = extract_pdf(path)
        if text.strip():
            verdicts[path.stem] = text
        else:
            print(f"警告：{path.name} 無法解析文字（可能是掃描圖片 PDF）")
    return verdicts


def run_strategy(client: openai.OpenAI, strategy_name: str, verdict_text: str) -> dict:
    prompt_fn = STRATEGIES[strategy_name]
    user_message = prompt_fn(verdict_text)

    start = time.time()
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=2048,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    elapsed = round(time.time() - start, 2)

    return {
        "strategy": strategy_name,
        "output": response.choices[0].message.content,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "elapsed_seconds": elapsed,
    }


def run_evidence_extraction(client: openai.OpenAI, verdict_text: str) -> dict:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=128,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": evidence_extraction(verdict_text)},
        ],
    )
    raw = response.choices[0].message.content

    decision = "不明"
    m = re.search(r"外遇認定:\s*\[?\s*([是否不明]+)", raw)
    if m:
        val = m.group(1).strip()
        if val.startswith("是"):
            decision = "是"
        elif val.startswith("否"):
            decision = "否"

    compensation = 0
    m = re.search(r"損害賠償金額:\s*\[?([\d,]+)", raw)
    if m:
        compensation = int(m.group(1).replace(",", ""))

    evidence_types = []
    m = re.search(r"證據類型:\s*(.+)", raw)
    if m:
        raw_types = m.group(1).strip()
        if raw_types != "無":
            evidence_types = [t.strip() for t in raw_types.split(",") if t.strip() and t.strip() != "無"]

    return {"decision": decision, "compensation": compensation, "evidence_types": evidence_types}


def run_eval(verdict_name: str, verdict_text: str, client: openai.OpenAI) -> dict:
    print(f"\n{'='*60}")
    print(f"判決書：{verdict_name}")
    print(f"{'='*60}")

    results = {"verdict": verdict_name, "strategies": [], "evidence": {}}

    print(f"  萃取證據要件 ...", end=" ", flush=True)
    results["evidence"] = run_evidence_extraction(client, verdict_text)
    ev = results["evidence"]
    print(f"完成（{ev['decision']}／賠償 {ev['compensation']:,}／證據 {ev['evidence_types']}）")

    for strategy_name in STRATEGIES:
        print(f"  執行策略：{strategy_name} ...", end=" ", flush=True)
        result = run_strategy(client, strategy_name, verdict_text)
        results["strategies"].append(result)
        print(f"完成（{result['elapsed_seconds']}s，"
              f"in={result['input_tokens']} out={result['output_tokens']}）")

    return results


def save_results(all_results: list[dict]) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON 完整結果
    json_path = RESULTS_DIR / f"外遇分析報告_{timestamp}.json"
    json_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 人類可讀的 Markdown 比較報告
    md_path = RESULTS_DIR / f"外遇分析報告_{timestamp}.md"
    lines = [f"# 外遇判決書 AI Eval 報告\n", f"執行時間：{timestamp}\n\n"]

    for verdict_result in all_results:
        lines.append(f"## 判決書：{verdict_result['verdict']}\n\n")
        for s in verdict_result["strategies"]:
            lines.append(f"### 策略：{s['strategy']}\n")
            lines.append(f"- 耗時：{s['elapsed_seconds']}s　"
                         f"輸入 tokens：{s['input_tokens']}　"
                         f"輸出 tokens：{s['output_tokens']}\n\n")
            lines.append(f"{s['output']}\n\n")
            lines.append("---\n\n")

    md_path.write_text("".join(lines), encoding="utf-8")

    save_html(all_results, timestamp, RESULTS_DIR)

    return md_path


def print_summary(all_results: list[dict]) -> None:
    print(f"\n{'='*60}")
    print("Token 使用量摘要")
    print(f"{'='*60}")
    print(f"{'策略':<20} {'平均輸入':>10} {'平均輸出':>10} {'平均耗時':>10}")
    print("-" * 55)

    strategy_names = list(STRATEGIES.keys())
    for name in strategy_names:
        rows = [
            s for r in all_results
            for s in r["strategies"] if s["strategy"] == name
        ]
        avg_in = sum(r["input_tokens"] for r in rows) / len(rows)
        avg_out = sum(r["output_tokens"] for r in rows) / len(rows)
        avg_t = sum(r["elapsed_seconds"] for r in rows) / len(rows)
        print(f"{name:<20} {avg_in:>10.0f} {avg_out:>10.0f} {avg_t:>9.1f}s")


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("請設定環境變數 OPENAI_API_KEY")

    client = openai.OpenAI(api_key=api_key)
    verdicts = load_verdicts()

    if not verdicts:
        print(f"找不到判決書！請將 .txt 或 .pdf 檔放入 {VERDICTS_DIR}/ 資料夾。")
        return

    print(f"找到 {len(verdicts)} 份判決書：{list(verdicts.keys())}")

    all_results = []
    for name, text in verdicts.items():
        result = run_eval(name, text, client)
        all_results.append(result)

    md_path = save_results(all_results)
    print_summary(all_results)
    print(f"\n結果已儲存至：{md_path}")


if __name__ == "__main__":
    main()
