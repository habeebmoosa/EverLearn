"""
Research Utility Tools

Provides text analysis utilities for evaluating research quality.
"""

import re
from typing import Optional


def count_words(text: str) -> dict:
    """
    Count words, sentences, and sections in a research document.

    Args:
        text: The text to analyze

    Returns:
        dict: Text statistics with keys:
            - word_count: Total words
            - sentence_count: Approximate sentence count
            - paragraph_count: Number of paragraphs
            - section_count: Number of markdown headings
            - char_count: Total characters

    Example:
        >>> count_words("This is a test. Another sentence.")
        {
            'word_count': 7,
            'sentence_count': 2,
            'paragraph_count': 1,
            'section_count': 0,
            'char_count': 33
        }
    """
    if not text:
        return {
            "word_count": 0,
            "sentence_count": 0,
            "paragraph_count": 0,
            "section_count": 0,
            "char_count": 0,
        }

    words = text.split()
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    sections = re.findall(r"^#{1,6}\s+.+", text, re.MULTILINE)

    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "section_count": len(sections),
        "char_count": len(text),
    }


def calculate_coverage_score(report: str, focus_areas: str) -> dict:
    """
    Calculate how well a report covers specified focus areas.

    Uses keyword frequency analysis to determine coverage.

    Args:
        report: The research report text to evaluate
        focus_areas: Comma-separated list of focus area keywords

    Returns:
        dict: Coverage analysis with keys:
            - overall_score: 0-100 coverage score
            - area_scores: per-area coverage details
            - covered_areas: number of areas covered
            - total_areas: total focus areas

    Example:
        >>> calculate_coverage_score("AI is transforming healthcare...", "AI,healthcare,regulation")
        {
            'overall_score': 67,
            'area_scores': [
                {'area': 'AI', 'mentions': 5, 'score': 100},
                {'area': 'healthcare', 'mentions': 3, 'score': 100},
                {'area': 'regulation', 'mentions': 0, 'score': 0}
            ],
            'covered_areas': 2,
            'total_areas': 3
        }
    """
    if not report or not focus_areas:
        return {"overall_score": 0, "area_scores": [], "covered_areas": 0, "total_areas": 0}

    areas = [a.strip() for a in focus_areas.split(",") if a.strip()]
    report_lower = report.lower()

    area_scores = []
    covered = 0

    for area in areas:
        area_lower = area.lower()
        # Count mentions (case-insensitive, whole word or partial)
        mentions = len(re.findall(re.escape(area_lower), report_lower))

        # Score: 0 mentions = 0, 1-2 = 50, 3-5 = 75, 6+ = 100
        if mentions == 0:
            score = 0
        elif mentions <= 2:
            score = 50
        elif mentions <= 5:
            score = 75
        else:
            score = 100

        if mentions > 0:
            covered += 1

        area_scores.append({
            "area": area,
            "mentions": mentions,
            "score": score,
        })

    overall = round(sum(a["score"] for a in area_scores) / len(area_scores)) if area_scores else 0

    return {
        "overall_score": overall,
        "area_scores": area_scores,
        "covered_areas": covered,
        "total_areas": len(areas),
    }


def extract_citations(text: str) -> dict:
    """
    Extract URLs, references, and source citations from text.

    Args:
        text: The text to scan for citations

    Returns:
        dict: Extracted citations with keys:
            - urls: list of URLs found
            - references: list of reference-style citations
            - citation_count: total citations found

    Example:
        >>> extract_citations("See https://example.com for details.")
        {
            'urls': ['https://example.com'],
            'references': [],
            'citation_count': 1
        }
    """
    if not text:
        return {"urls": [], "references": [], "citation_count": 0}

    # Extract URLs
    url_pattern = re.compile(r"https?://[^\s\)\]\>\"',]+")
    urls = list(set(url_pattern.findall(text)))

    # Extract markdown-style references [text](url)
    md_refs = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
    references = [{"text": ref[0], "url": ref[1]} for ref in md_refs]

    # Extract numbered references like [1], [2]
    numbered_refs = re.findall(r"\[(\d+)\]", text)

    return {
        "urls": urls,
        "references": references,
        "numbered_references": list(set(numbered_refs)),
        "citation_count": len(urls) + len(references),
    }


def chunk_text(text: str, chunk_size: int = 5000, overlap: int = 500) -> dict:
    """
    Split large text into overlapping chunks for processing.

    Args:
        text: The text to split
        chunk_size: Maximum characters per chunk (default 5000)
        overlap: Characters of overlap between chunks (default 500)

    Returns:
        dict: Chunked text with keys:
            - chunks: list of text chunks
            - chunk_count: number of chunks
            - total_chars: original text length

    Example:
        >>> chunk_text("Long text here...", chunk_size=100, overlap=20)
        {
            'chunks': ['Long text...', '...text here...'],
            'chunk_count': 2,
            'total_chars': 150
        }
    """
    if not text:
        return {"chunks": [], "chunk_count": 0, "total_chars": 0}

    if len(text) <= chunk_size:
        return {"chunks": [text], "chunk_count": 1, "total_chars": len(text)}

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap

    return {
        "chunks": chunks,
        "chunk_count": len(chunks),
        "total_chars": len(text),
    }
