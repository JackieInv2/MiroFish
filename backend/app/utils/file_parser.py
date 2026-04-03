"""
文件解析工具
支持PDF、Markdown、TXT文件的文本提取
Enhanced for investment research PDFs (earnings reports, analyst reports, 10-K filings).
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional


def _read_text_with_fallback(file_path: str) -> str:
    """
    读取文本文件，UTF-8失败时自动探测编码。

    采用多级回退策略：
    1. 首先尝试 UTF-8 解码
    2. 使用 charset_normalizer 检测编码
    3. 回退到 chardet 检测编码
    4. 最终使用 UTF-8 + errors='replace' 兜底
    """
    data = Path(file_path).read_bytes()

    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass

    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception:
        pass

    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass

    if not encoding:
        encoding = 'utf-8'

    return data.decode(encoding, errors='replace')


class FileParser:
    """文件解析器"""

    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}

    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """从文件中提取文本"""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        suffix = path.suffix.lower()

        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {suffix}")

        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)

        raise ValueError(f"无法处理的文件格式: {suffix}")

    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """从PDF提取文本"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("需要安装PyMuPDF: pip install PyMuPDF")

        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """从Markdown提取文本，支持自动编码检测"""
        return _read_text_with_fallback(file_path)

    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """从TXT提取文本，支持自动编码检测"""
        return _read_text_with_fallback(file_path)

    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """从多个文件提取文本并合并"""
        all_texts = []

        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== 文档 {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== 文档 {i}: {file_path} (提取失败: {str(e)}) ===")

        return "\n\n".join(all_texts)

    # ------------------------------------------------------------------
    # Investment PDF extraction helpers
    # ------------------------------------------------------------------

    @classmethod
    def extract_investment_brief(cls, file_path: str) -> Dict[str, str]:
        """Extract structured investment brief from a research PDF.

        Returns a dict with keys like 'full_text', 'financial_data',
        'risk_factors', 'management_discussion', 'summary'.
        """
        full_text = cls.extract_text(file_path)
        return cls._parse_investment_sections(full_text)

    @staticmethod
    def _parse_investment_sections(text: str) -> Dict[str, str]:
        """Heuristically extract common investment research sections."""
        sections: Dict[str, str] = {"full_text": text}

        # Common section heading patterns in research reports / 10-K filings
        section_patterns = {
            "financial_data": [
                r"(?i)(?:financial\s+(?:highlights?|summary|data|statements?|results?))",
                r"(?i)(?:income\s+statement|balance\s+sheet|cash\s+flow)",
                r"(?i)(?:revenue|earnings|EPS|EBITDA)",
            ],
            "risk_factors": [
                r"(?i)(?:risk\s+factors?)",
                r"(?i)(?:principal\s+risks?|key\s+risks?)",
            ],
            "management_discussion": [
                r"(?i)(?:management(?:'s)?\s+discussion)",
                r"(?i)(?:MD&A|management\s+analysis)",
                r"(?i)(?:business\s+overview|company\s+overview)",
            ],
            "valuation": [
                r"(?i)(?:valuation|price\s+target|target\s+price)",
                r"(?i)(?:DCF|discounted\s+cash\s+flow|comparable|comps)",
            ],
            "recommendation": [
                r"(?i)(?:investment\s+(?:thesis|recommendation|conclusion))",
                r"(?i)(?:our\s+(?:view|recommendation|rating))",
                r"(?i)(?:buy|sell|hold|overweight|underweight)\s+(?:rating|recommendation)",
            ],
        }

        lines = text.split("\n")

        for section_name, patterns in section_patterns.items():
            collected: List[str] = []
            capturing = False
            blank_count = 0

            for line in lines:
                stripped = line.strip()

                if not capturing:
                    for pat in patterns:
                        if re.search(pat, stripped):
                            capturing = True
                            collected.append(stripped)
                            blank_count = 0
                            break
                else:
                    if not stripped:
                        blank_count += 1
                        if blank_count > 3:
                            capturing = False
                            continue
                    else:
                        blank_count = 0

                    # Stop if we hit what looks like a new major section header
                    if (
                        len(stripped) < 80
                        and stripped.isupper()
                        and len(collected) > 5
                    ):
                        capturing = False
                        continue

                    collected.append(stripped)

                    # Limit section extraction to ~150 lines
                    if len(collected) > 150:
                        capturing = False

            if collected:
                sections[section_name] = "\n".join(collected)

        # Generate a summary snippet (first ~500 chars after any boilerplate)
        summary_text = text[:2000].strip()
        sections.setdefault("summary", summary_text[:500])

        return sections


def split_text_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[str]:
    """将文本分割成小块"""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end < len(text) else len(text)

    return chunks
