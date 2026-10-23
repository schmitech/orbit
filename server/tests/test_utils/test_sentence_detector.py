"""Tests for the streaming sentence detector used to feed TTS."""

import pytest
from utils.sentence_detector import SentenceDetector, extract_sentences


@pytest.mark.parametrize("text, expected", [
    # Words that merely end like an abbreviation are not abbreviations.
    ("We finished. Next steps follow.", ["We finished.", "Next steps follow."]),
    ("Check the items. Then continue.", ["Check the items.", "Then continue."]),
    ("I moved to Mexico. It was nice.", ["I moved to Mexico.", "It was nice."]),
    ("This is the first. Second one here.", ["This is the first.", "Second one here."]),
    ("Open the app. It loads.", ["Open the app.", "It loads."]),
])
def test_words_ending_like_abbreviations_end_sentences(text, expected):
    assert extract_sentences(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Dr. Smith is here. He waits.", ["Dr. Smith is here.", "He waits."]),
    ("Use e.g. this one. Done.", ["Use e.g. this one.", "Done."]),
    ("Meet at 5 p.m. tomorrow. Bye.", ["Meet at 5 p.m. tomorrow.", "Bye."]),
    ("(see vol. 2) Read it. Ok.", ["(see vol. 2) Read it.", "Ok."]),
    ("—Dr. Smith is here. He waits.", ["—Dr. Smith is here.", "He waits."]),
    ("*Dr. Smith is here. He waits.", ["*Dr. Smith is here.", "He waits."]),
])
def test_real_abbreviations_do_not_end_sentences(text, expected):
    assert extract_sentences(text) == expected


def test_streamed_chunks_split_the_same_way():
    detector = SentenceDetector()
    out = []
    for chunk in ["We fini", "shed. Ne", "xt one. "]:
        out.extend(detector.add_text(chunk))
    assert out == ["We finished.", "Next one."]


@pytest.mark.parametrize("text", [".", " .", "   "])
def test_empty_or_whitespace_before_period_does_not_crash(text):
    extract_sentences(text)
