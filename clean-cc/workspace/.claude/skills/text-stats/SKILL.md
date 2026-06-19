---
name: text-stats
description: Summarize a block of text — count characters, words, and lines, and report the longest line. Trigger when the user asks for text statistics, a word/line/character count, or a quick size summary of a text. Do not trigger for prose summarization or content questions.
---

# Text stats

The user provides a block of text. Produce a small report:

1. Count characters (including whitespace), words (whitespace-separated), and lines.
2. Identify the longest line (by character count) and its length.
3. Output a markdown table of the metrics, then a one-line verdict based on word
   count: `< 50` = short note, `50–500` = paragraph, `> 500` = long document.
