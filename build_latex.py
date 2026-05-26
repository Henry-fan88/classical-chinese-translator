"""阶段三：把译文按原书结构组装成 LaTeX。

结构映射（与 EPUB 分段一一对应）：
  juan    -> \\chapter         （卷）
  heading -> \\section/...      （序、章标题）
  byline  -> \\byline           （右对齐小字署名）
  para    -> 一个段落
  verse   -> verse 环境（保留分行）

用法：
  python build_latex.py              # 仅译文（简体白话）
  python build_latex.py --bilingual  # 原文 + 译文对照（便于校对）
"""
import sys

import config
import store

PREAMBLE = r"""\documentclass[UTF8,fontset=mac,a4paper,12pt,openany]{ctexbook}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage{xeCJK}
\usepackage{verse}
\linespread{1.35}
\setlength{\parskip}{0.4em}
\ctexset{
  chapter/format = \raggedright\bfseries\Large,
  section/format = \raggedright\bfseries\large,
}
% 署名：右对齐小字
\newcommand{\byline}[1]{{\par\raggedleft\small\itshape #1\par}}
% 原文小字（对照模式用）
\newcommand{\orig}[1]{{\par\small\color{gray} 原文：#1\par}}
\usepackage{xcolor}
\title{宗镜录\\[6pt]\large 简体白话译本}
\author{〔五代〕永明延寿 集\\ DeepSeek 机器翻译}
\date{}
"""

FRONT = r"""\begin{document}
\maketitle
\thispagestyle{empty}
\vspace*{2cm}
\begin{center}\small
本电子书原文出自 CBETA 电子佛典《大正藏》 T48 No.2016《宗镜录》（公有领域）。\\
白话译文为 DeepSeek 模型自动翻译，仅供阅读参考，未经人工校订，\\
义理以原典为准。
\end{center}
\clearpage
\tableofcontents
\clearpage
"""

_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def esc(s: str) -> str:
    out = []
    for ch in s:
        out.append(_SPECIAL.get(ch, ch))
    return "".join(out)


def main():
    bilingual = "--bilingual" in sys.argv
    conn = store.connect(readonly=True)
    rows = conn.execute(
        "SELECT juan_no,kind,level,source,translated,status FROM segments ORDER BY seq"
    ).fetchall()
    conn.close()
    if not rows:
        raise SystemExit("状态库为空，请先运行 extract.py。")

    body = []
    chapter_open = False
    pre_done = False
    missing = 0

    for r in rows:
        kind, lvl = r["kind"], r["level"]
        text = r["translated"] if r["status"] == "done" and r["translated"] else r["source"]
        if r["status"] != "done":
            missing += 1
        text = text.strip()
        if not text:
            continue

        if kind == "juan":
            body.append(f"\n\\chapter{{{esc(text)}}}\n")
            chapter_open = True
        elif kind == "heading":
            if not chapter_open and not pre_done:
                body.append("\n\\chapter*{卷前序文}\n"
                            "\\addcontentsline{toc}{chapter}{卷前序文}\n")
                pre_done = True
            cmd = {1: "section", 2: "subsection", 3: "subsubsection"}.get(lvl, "paragraph")
            star = "*" if not chapter_open else ""
            body.append(f"\\{cmd}{star}{{{esc(text)}}}\n")
        elif kind == "byline":
            body.append(f"\\byline{{{esc(text)}}}\n")
        elif kind == "verse":
            lines = [esc(l) for l in text.split("\n") if l.strip()]
            body.append("\\begin{verse}\n" + " \\\\\n".join(lines) + "\n\\end{verse}\n")
            if bilingual:
                body.append(f"\\orig{{{esc(r['source'])}}}\n")
        else:  # para
            body.append(esc(text) + "\n")
            if bilingual:
                body.append(f"\\orig{{{esc(r['source'])}}}\n")

    tex = PREAMBLE + FRONT + "\n".join(body) + "\n\\end{document}\n"
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    config.TEX_PATH.write_text(tex, encoding="utf-8")

    print(f"已生成 LaTeX: {config.TEX_PATH}")
    print(f"  段落 {len(rows)}，其中未翻译 {missing}（未译段落会暂时填入原文）。")
    if missing:
        print("  提示：翻译尚未全部完成，可等完成后再重建以获得纯白话版。")
    print(f"  模式: {'原文/译文对照' if bilingual else '仅白话译文'}")
    print("\n下一步编译 PDF:  bash build_pdf.sh")


if __name__ == "__main__":
    main()
