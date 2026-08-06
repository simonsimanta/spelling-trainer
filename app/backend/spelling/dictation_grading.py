from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Optional


WORD_PATTERN = re.compile(r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*")
PUNCTUATION_PATTERN = re.compile(r"[.,!?;:]")


@dataclass(frozen=True)
class WordToken:
    raw: str
    normalized: str
    index: int


@dataclass(frozen=True)
class WordOperation:
    operation: str
    expected: Optional[str]
    actual: Optional[str]
    expected_index: Optional[int]
    actual_index: Optional[int]
    confidence: float


@dataclass(frozen=True)
class TargetGrade:
    target: str
    actual: Optional[str]
    is_correct: bool
    error_type: Optional[str]
    confidence: float
    expected_index: Optional[int]

    @property
    def feeds_practice(self) -> bool:
        return self.error_type == "substitution" and self.confidence >= 0.7


@dataclass(frozen=True)
class DictationGrade:
    word_error_rate: float
    word_accuracy: float
    capitalization_accuracy: float
    punctuation_accuracy: float
    omissions: int
    additions: int
    substitutions: int
    expected_word_count: int
    attempt_word_count: int
    operations: list[WordOperation]
    targets: list[TargetGrade]

    @property
    def target_accuracy(self) -> float:
        if not self.targets:
            return 0.0
        return round(sum(target.is_correct for target in self.targets) / len(self.targets), 4)


def word_tokens(value: str) -> list[WordToken]:
    return [
        WordToken(
            raw=match.group(0),
            normalized=match.group(0).lower().replace("\u2019", "'"),
            index=index,
        )
        for index, match in enumerate(WORD_PATTERN.finditer(value))
    ]


def split_sentence_segments(value: str) -> list[str]:
    segments = [segment.strip() for segment in re.findall(r"[^.!?]+(?:[.!?]+|$)", value)]
    return [segment for segment in segments if segment]


def _substitution_confidence(expected: str, actual: str) -> float:
    return round(SequenceMatcher(None, expected.lower(), actual.lower()).ratio(), 4)


def align_words(expected_text: str, attempt_text: str) -> list[WordOperation]:
    expected = word_tokens(expected_text)
    actual = word_tokens(attempt_text)
    rows = len(expected) + 1
    columns = len(actual) + 1
    costs = [[0] * columns for _ in range(rows)]
    pointers: list[list[Optional[str]]] = [[None] * columns for _ in range(rows)]

    for index in range(1, rows):
        costs[index][0] = index
        pointers[index][0] = "omission"
    for index in range(1, columns):
        costs[0][index] = index
        pointers[0][index] = "addition"

    for expected_index in range(1, rows):
        for actual_index in range(1, columns):
            equal = expected[expected_index - 1].normalized == actual[actual_index - 1].normalized
            diagonal = costs[expected_index - 1][actual_index - 1] + (0 if equal else 1)
            omission = costs[expected_index - 1][actual_index] + 1
            addition = costs[expected_index][actual_index - 1] + 1
            best = min(diagonal, omission, addition)
            costs[expected_index][actual_index] = best
            if diagonal == best:
                pointers[expected_index][actual_index] = "equal" if equal else "substitution"
            elif omission == best:
                pointers[expected_index][actual_index] = "omission"
            else:
                pointers[expected_index][actual_index] = "addition"

    operations: list[WordOperation] = []
    expected_index = len(expected)
    actual_index = len(actual)
    while expected_index > 0 or actual_index > 0:
        operation = pointers[expected_index][actual_index]
        if operation in {"equal", "substitution"}:
            expected_token = expected[expected_index - 1]
            actual_token = actual[actual_index - 1]
            operations.append(
                WordOperation(
                    operation=operation,
                    expected=expected_token.raw,
                    actual=actual_token.raw,
                    expected_index=expected_token.index,
                    actual_index=actual_token.index,
                    confidence=(
                        1.0
                        if operation == "equal"
                        else _substitution_confidence(expected_token.normalized, actual_token.normalized)
                    ),
                )
            )
            expected_index -= 1
            actual_index -= 1
        elif operation == "omission":
            expected_token = expected[expected_index - 1]
            operations.append(
                WordOperation(
                    operation="omission",
                    expected=expected_token.raw,
                    actual=None,
                    expected_index=expected_token.index,
                    actual_index=None,
                    confidence=0.0,
                )
            )
            expected_index -= 1
        else:
            actual_token = actual[actual_index - 1]
            operations.append(
                WordOperation(
                    operation="addition",
                    expected=None,
                    actual=actual_token.raw,
                    expected_index=None,
                    actual_index=actual_token.index,
                    confidence=0.0,
                )
            )
            actual_index -= 1
    return list(reversed(operations))


def _edit_distance(expected: list[str], actual: list[str]) -> int:
    previous = list(range(len(actual) + 1))
    for expected_index, expected_value in enumerate(expected, start=1):
        current = [expected_index]
        for actual_index, actual_value in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[actual_index] + 1,
                    previous[actual_index - 1] + (expected_value != actual_value),
                )
            )
        previous = current
    return previous[-1]


def _target_grade(target: str, operations: list[WordOperation]) -> TargetGrade:
    normalized = target.lower().replace("\u2019", "'")
    matching = [
        operation
        for operation in operations
        if operation.expected and operation.expected.lower().replace("\u2019", "'") == normalized
    ]
    substitution = next(
        (operation for operation in matching if operation.operation == "substitution"),
        None,
    )
    if substitution:
        return TargetGrade(
            target,
            substitution.actual,
            False,
            "substitution",
            substitution.confidence,
            substitution.expected_index,
        )
    omission = next((operation for operation in matching if operation.operation == "omission"), None)
    if omission:
        return TargetGrade(target, None, False, "omission", 0.0, omission.expected_index)
    exact = next((operation for operation in matching if operation.operation == "equal"), None)
    if exact:
        return TargetGrade(target, exact.actual, True, None, 1.0, exact.expected_index)
    return TargetGrade(
        target,
        None,
        False,
        "omission",
        0.0,
        None,
    )


def grade_dictation(
    expected_text: str,
    attempt_text: str,
    target_terms: list[str],
) -> DictationGrade:
    expected = word_tokens(expected_text)
    actual = word_tokens(attempt_text)
    operations = align_words(expected_text, attempt_text)
    omissions = sum(operation.operation == "omission" for operation in operations)
    additions = sum(operation.operation == "addition" for operation in operations)
    substitutions = sum(operation.operation == "substitution" for operation in operations)
    errors = omissions + additions + substitutions
    denominator = max(len(expected), 1)
    word_error_rate = round(errors / denominator, 4)
    word_accuracy = round(max(0.0, 1.0 - word_error_rate), 4)
    capitalization_comparisons = [
        operation
        for operation in operations
        if operation.operation == "equal" and operation.expected is not None
    ]
    capitalization_correct = sum(
        operation.expected == operation.actual for operation in capitalization_comparisons
    )
    capitalization_accuracy = round(
        capitalization_correct / max(len(capitalization_comparisons), 1),
        4,
    )
    expected_punctuation = PUNCTUATION_PATTERN.findall(expected_text)
    actual_punctuation = PUNCTUATION_PATTERN.findall(attempt_text)
    punctuation_errors = _edit_distance(expected_punctuation, actual_punctuation)
    punctuation_accuracy = round(
        max(0.0, 1.0 - (punctuation_errors / max(len(expected_punctuation), 1))),
        4,
    )
    return DictationGrade(
        word_error_rate=word_error_rate,
        word_accuracy=word_accuracy,
        capitalization_accuracy=capitalization_accuracy,
        punctuation_accuracy=punctuation_accuracy,
        omissions=omissions,
        additions=additions,
        substitutions=substitutions,
        expected_word_count=len(expected),
        attempt_word_count=len(actual),
        operations=operations,
        targets=[_target_grade(target, operations) for target in target_terms],
    )
