"""阶段一：解析 EPUB，把每一段落按原书顺序写入状态库。

只处理 OEBPS/juans/*.xhtml（正文 100 卷），跳过 CBETA 的版权页/封面。
还原规则（与 cbeta.css 对应）：
  <div class='juan'>  -> 卷标题 (kind=juan)
  <p class='hN'>      -> 序/章标题 (kind=heading, level=N)
  <p class='byline'>  -> 署名 (kind=byline)
  <div class='lg'>    -> 偈颂 (kind=verse，保留分行)
  其它无子块的 <div>   -> 正文段落 (kind=para)
"""
import re
import sys
import zipfile

from bs4 import BeautifulSoup, NavigableString, Tag

import config
import store


def _classes(tag: Tag):
    c = tag.get("class")
    if not c:
        return []
    return c if isinstance(c, list) else [c]


def _text(tag: Tag) -> str:
    """取纯文本：保留 corr 校勘字，丢弃锚点，规整空白。"""
    s = tag.get_text()
    s = s.replace("　", "").strip()
    s = re.sub(r"[ \t]+", "", s)        # 中文无需空格
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def _verse_text(tag: Tag) -> str:
    """偈颂：每个 lg-row 一行。"""
    rows = tag.find_all(class_="lg-row")
    if not rows:
        return _text(tag)
    lines = [_text(r) for r in rows]
    return "\n".join(l for l in lines if l)


def _has_block_child(tag: Tag) -> bool:
    return any(isinstance(c, Tag) and c.name in ("div", "p") for c in tag.children)


def _walk(node: Tag, out: list):
    """按文档顺序递归，产出 (kind, level, text) 列表。"""
    for child in node.children:
        if not isinstance(child, Tag):
            continue
        cls = _classes(child)
        if child.name == "p":
            txt = _text(child)
            if not txt:
                continue
            if "byline" in cls:
                out.append(("byline", 0, txt))
            else:
                m = [c for c in cls if re.fullmatch(r"h[1-5]", c)]
                if m:
                    out.append(("heading", int(m[0][1]), txt))
                else:
                    out.append(("para", 0, txt))
        elif child.name == "div":
            if "juan" in cls:
                txt = _text(child)
                if txt:
                    out.append(("juan", 0, txt))
            elif "lg" in cls:
                txt = _verse_text(child)
                if txt:
                    out.append(("verse", 0, txt))
            elif _has_block_child(child):
                _walk(child, out)          # 容器，继续下钻
            else:
                txt = _text(child)
                if txt:
                    out.append(("para", 0, txt))


def parse_epub() -> list:
    """返回全书有序的段落列表：dict(juan_no, local_no, kind, level, source)。"""
    zf = zipfile.ZipFile(config.EPUB_PATH)
    names = sorted(n for n in zf.namelist()
                   if re.match(r"OEBPS/juans/\d+\.xhtml$", n))
    if not names:
        raise SystemExit("未在 EPUB 中找到 juans/*.xhtml，请检查文件。")

    segments = []
    for jn, name in enumerate(names, start=1):
        html = zf.read(name).decode("utf-8", "replace")
        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("div", id="body") or soup.body
        units = []
        _walk(body, units)
        # 每卷卷尾会重复一次卷标题（紧跟刻印牌记），只保留卷首那个，去掉重复
        seen_juan = False
        kept = []
        for kind, level, text in units:
            if kind == "juan":
                if seen_juan:
                    continue
                seen_juan = True
            kept.append((kind, level, text))
        units = kept
        for ln, (kind, level, text) in enumerate(units, start=1):
            segments.append(dict(juan_no=jn, local_no=ln, kind=kind,
                                 level=level, source=text))
    zf.close()
    return segments


def main():
    print(f"读取 EPUB: {config.EPUB_PATH}")
    segs = parse_epub()
    store.init()
    conn = store.connect()

    existing = conn.execute("SELECT COUNT(*) n FROM segments").fetchone()["n"]
    if existing and "--force" not in sys.argv:
        print(f"状态库已有 {existing} 段。如需重建请加 --force（会清空已有译文）。")
        conn.close()
        return
    if "--force" in sys.argv:
        conn.execute("DELETE FROM segments")

    now = 0.0
    rows = []
    for seq, s in enumerate(segs, start=1):
        rows.append((s["juan_no"], seq, s["local_no"], s["kind"], s["level"],
                     s["source"], len(s["source"]), now))
    conn.executemany(
        "INSERT INTO segments(juan_no,seq,local_no,kind,level,source,n_chars,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)", rows)
    store.set_meta(conn, "epub", str(config.EPUB_PATH))
    conn.commit()

    st = store.stats(conn)
    n_juan = conn.execute("SELECT COUNT(DISTINCT juan_no) n FROM segments").fetchone()["n"]
    kinds = conn.execute("SELECT kind, COUNT(*) n FROM segments GROUP BY kind").fetchall()
    conn.close()

    # 成本估算
    chars = st["total_c"]
    in_tok = chars * config.CHARS_PER_TOKEN
    out_tok = chars * config.OUTPUT_RATIO * config.CHARS_PER_TOKEN
    cost = in_tok / 1e6 * config.PRICE_INPUT_PER_M + out_tok / 1e6 * config.PRICE_OUTPUT_PER_M

    print("\n========== 抽取完成 ==========")
    print(f"卷数        : {n_juan}")
    print(f"段落总数    : {st['total_n']}")
    print(f"原文总字数  : {chars:,}")
    print("分类        : " + ", ".join(f"{k['kind']}={k['n']}" for k in kinds))
    print("------------------------------")
    print(f"预估输入token: ~{in_tok/1e6:.2f} M")
    print(f"预估输出token: ~{out_tok/1e6:.2f} M（按 {config.OUTPUT_RATIO}x 估）")
    print(f"预估费用    : ~¥{cost:.1f}  "
          f"(单价 in ¥{config.PRICE_INPUT_PER_M}/M, out ¥{config.PRICE_OUTPUT_PER_M}/M，"
          f"以官网为准；DeepSeek 命中缓存会更便宜)")
    print("==============================")


if __name__ == "__main__":
    main()
