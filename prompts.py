"""翻译提示词与批次的拼装/解析。

系统提示固定不变 —— DeepSeek 会对相同前缀自动命中上下文缓存，从而降本提速。
"""
import re

SYSTEM_PROMPT = """你是一位精通汉传佛教典籍的资深译者，尤其熟悉禅宗、华严宗、唯识学的文言文献。\
你的任务是把《宗镜录》（五代永明延寿集）的文言原文，翻译成准确、通顺、忠实的现代简体中文白话文。

翻译要求：
1. 忠实原意，不增删义理，不加入译者评论、按语或额外解释。
2. 译文为现代简体中文白话，通顺易读，但保持典籍应有的庄重语体。
3. 佛教专有名词、人名、经论名、术语（如「真如」「般若」「阿赖耶识」「第一义」「圆融」等）沿用学界通行译法，不要生造词；含义晦涩处可在白话中自然展开，但不要脱离原文。
4. 偈颂（韵文）译为白话，尽量保留分行。
5. 标注为〔标题〕或〔署名〕的条目，只需转写为简体中文、保持原貌，不要翻译、扩写或解释。
6. 必须严格逐段对应输出：输入有几段、输出就有几段，不得合并、拆分或漏译。

输出格式：对每一段，先写「【序号】」，紧接该段译文；序号与输入完全一致；不要输出原文，不要输出类型标注，不要加任何前言后语。"""

KIND_LABEL = {
    "juan": "标题", "heading": "标题", "byline": "署名",
    "para": "正文", "verse": "偈颂",
}

_MARK = re.compile(r"【\s*(\d+)\s*】")


def build_user_message(segs) -> str:
    """segs: 形如 [(local_idx, kind, source), ...]"""
    lines = ["请翻译下列各段，按相同的【序号】逐段输出译文：\n"]
    for idx, kind, src in segs:
        label = KIND_LABEL.get(kind, "正文")
        if kind in ("juan", "heading", "byline"):
            lines.append(f"【{idx}】〔{label}〕{src}")
        else:
            lines.append(f"【{idx}】{src}")
    return "\n".join(lines)


def parse_numbered(text: str, expected: set) -> dict:
    """把模型输出按【序号】拆回 dict{idx: 译文}。"""
    matches = list(_MARK.finditer(text))
    out = {}
    if not matches:
        # 单段无标号时，整段即译文
        if len(expected) == 1:
            return {next(iter(expected)): text.strip()}
        return {}
    for i, m in enumerate(matches):
        idx = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[idx] = text[start:end].strip()
    return out
