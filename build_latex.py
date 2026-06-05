"""阶段三：把译文按原书结构组装成 LaTeX。

结构映射（与 EPUB 分段一一对应）：
  juan    -> \\chapter         （卷）
  heading -> \\section/...      （序、章标题）
  byline  -> \\byline           （右对齐小字署名）
  para    -> 一个段落
  verse   -> verse 环境（保留分行）

用法：
  python build_latex.py              # 仅译文（简体白话）-> output/zongjinglu.tex
  python build_latex.py --bilingual  # 原文/译文对照     -> output/zongjinglu_bilingual.tex

字号：默认 14pt。基于 extbook 类（支持大字号）+ ctex 宏包。用环境变量覆盖：
  TR_FONT_PT=17 python build_latex.py --bilingual
extbook 可选字号：10 / 11 / 12 / 14 / 17 / 20 (pt)。需要 extsizes 宏包
（TinyTeX 用户：tlmgr install extsizes）。
"""
import os
import sys

import config
import store

# 全局基础字号（pt），可用环境变量覆盖。默认 14pt（比原 12pt 大一档）。
FONT_PT = os.environ.get("TR_FONT_PT", "14")


def preamble(bilingual: bool) -> str:
    subtitle = "原文／白话对照本" if bilingual else "简体白话译本"
    # 对照模式额外定义：原文用灰色，译文用黑色，成对排版便于对读。
    bil_macros = r"""
\definecolor{srccolor}{gray}{0.40}
% 对照：原文（灰）紧跟译文（黑），段尾留白把每一对隔开
\newcommand{\srcpar}[1]{{\par\color{srccolor}#1\par}}
\newcommand{\trpar}[1]{{\par #1\par}}
\newcommand{\bilgap}{\vspace{0.5em}}
""" if bilingual else ""
    # extbook 提供 14/17/20pt 等大字号，再用 ctex 宏包加中文支持（heading=true
    # 复现 ctexbook 的「第 N 章」中文章节样式并启用 \ctexset 章节键）。
    return (
        r"\documentclass[a4paper," + FONT_PT + r"pt,openany]{extbook}"
        + r"""
\usepackage[UTF8,fontset=mac,heading=true]{ctex}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage{xcolor}
\usepackage{verse}
\linespread{1.35}
\setlength{\parskip}{0.4em}
\ctexset{
  chapter/format = \raggedright\bfseries\Large,
  section/format = \raggedright\bfseries\large,
}
% 署名：右对齐小字
\newcommand{\byline}[1]{{\par\raggedleft\small\itshape #1\par}}
"""
        + bil_macros
        + r"\title{宗镜录\\[6pt]\large " + subtitle + r"}"
        + r"""
\author{〔五代〕永明延寿 集\\ DeepSeek 机器翻译}
\date{}
"""
    )


def front(bilingual: bool) -> str:
    convention = (
        r"\vspace{1em}本对照本：\textcolor{srccolor}{灰色为原文（繁体）}，黑色为白话译文。\\"
        if bilingual else ""
    )
    return (
        r"""\begin{document}
\maketitle
\thispagestyle{empty}
\vspace*{2cm}
\begin{center}\small
本电子书原文出自 CBETA 电子佛典《大正藏》 T48 No.2016《宗镜录》（公有领域）。\\
白话译文为 DeepSeek 模型自动翻译，仅供阅读参考，未经人工校订，\\
义理以原典为准。"""
        + convention
        + r"""
\end{center}
\clearpage
\tableofcontents
\clearpage
"""
    )


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


def verse_env(text: str, color_cmd: str = "") -> str:
    lines = [esc(l) for l in text.split("\n") if l.strip()]
    inner = " \\\\\n".join(lines)
    if color_cmd:
        inner = "{" + color_cmd + " " + inner + "}"
    return "\\begin{verse}\n" + inner + "\n\\end{verse}\n"


def main():
    bilingual = "--bilingual" in sys.argv
    out_path = (config.OUT_DIR / "zongjinglu_bilingual.tex") if bilingual else config.TEX_PATH

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
            if bilingual:
                body.append(verse_env(r["source"], r"\color{srccolor}"))
                body.append(verse_env(text))
                body.append("\\bilgap\n")
            else:
                body.append(verse_env(text))
        else:  # para
            if bilingual:
                body.append(f"\\srcpar{{{esc(r['source'])}}}\n")
                body.append(f"\\trpar{{{esc(text)}}}\n")
                body.append("\\bilgap\n")
            else:
                body.append(esc(text) + "\n")

    tex = preamble(bilingual) + front(bilingual) + "\n".join(body) + "\n\\end{document}\n"
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(tex, encoding="utf-8")

    print(f"已生成 LaTeX: {out_path}")
    print(f"  段落 {len(rows)}，其中未翻译 {missing}（未译段落会暂时填入原文）。")
    if missing:
        print("  提示：翻译尚未全部完成，可等完成后再重建以获得纯白话版。")
    print(f"  模式: {'原文/译文对照' if bilingual else '仅白话译文'}，基础字号 {FONT_PT}pt")
    print(f"\n下一步编译 PDF:  bash build_pdf.sh {out_path.stem}")


if __name__ == "__main__":
    main()
