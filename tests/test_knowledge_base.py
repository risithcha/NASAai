"""Tests for knowledge.knowledge_base batching logic."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from knowledge.knowledge_base import KnowledgeBase


def _fake_encoding():
    """Return a mock tiktoken encoder that counts whitespace-separated words."""
    enc = MagicMock()
    enc.encode = lambda text: text.split()  # 1 token per word
    return enc


@pytest.fixture(autouse=True)
def _mock_tiktoken():
    """Patch tiktoken so tests don't need a network connection."""
    with patch("tiktoken.encoding_for_model", return_value=_fake_encoding()):
        yield


class TestBuildTokenBatches:
    """Unit tests for _build_token_batches, the token-aware batch splitter."""

    def test_single_small_text_returns_one_batch(self):
        texts = ["hello world"]  # 2 "tokens"
        batches = KnowledgeBase._build_token_batches(texts, max_tokens=100)
        assert len(batches) == 1
        assert batches[0] == texts

    def test_empty_input_returns_empty(self):
        batches = KnowledgeBase._build_token_batches([], max_tokens=100)
        assert batches == []

    def test_splits_when_exceeding_limit(self):
        # 10 words = 10 tokens per chunk
        chunk = " ".join(f"w{i}" for i in range(10))
        texts = [chunk] * 10  # 100 tokens total
        batches = KnowledgeBase._build_token_batches(texts, max_tokens=25)
        # 25 / 10 = 2 texts per batch → 5 batches
        assert len(batches) > 1
        # All texts should be preserved across batches
        flat = [t for b in batches for t in b]
        assert flat == texts

    def test_all_texts_preserved(self):
        texts = [f"text number {i}" for i in range(50)]  # 3 tokens each
        batches = KnowledgeBase._build_token_batches(texts, max_tokens=10)
        flat = [t for b in batches for t in b]
        assert flat == texts

    def test_single_oversized_text_still_included(self):
        # A single text that exceeds max_tokens should still end up in its
        # own batch (we can't split individual texts here).
        big = " ".join(f"w{i}" for i in range(500))  # 500 "tokens"
        texts = [big]
        batches = KnowledgeBase._build_token_batches(texts, max_tokens=100)
        assert len(batches) == 1
        assert batches[0] == [big]

    def test_respects_token_limit(self):
        # Each chunk is 20 words = 20 tokens
        chunk = " ".join(f"word{i}" for i in range(20))
        texts = [chunk] * 20
        max_tokens = 50
        batches = KnowledgeBase._build_token_batches(texts, max_tokens=max_tokens)
        for batch in batches:
            total = sum(len(t.split()) for t in batch)
            # Only single-item batches may exceed the limit (unavoidable)
            if len(batch) > 1:
                assert total <= max_tokens

    def test_exact_boundary(self):
        # 5 tokens each, limit 10 → exactly 2 per batch
        texts = ["a b c d e"] * 6
        batches = KnowledgeBase._build_token_batches(texts, max_tokens=10)
        assert len(batches) == 3
        for batch in batches:
            assert len(batch) == 2
