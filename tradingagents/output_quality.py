"""Deterministic, intentionally limited checks for generated research reports.

The rules recognize a small set of numeric and holdings phrases in Korean and
English. They surface review candidates; they do not establish factual or
semantic correctness.
"""

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from tradingagents.dataflows.symbols import normalize_symbol

_NUMBER_RE = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?")
_CLAIM_RE = re.compile(
    r"(?:%|\$|€|£|₩|\b(?:usd|krw|eur|gbp|jpy)\b|"
    r"\b(?:price|priced|target|probability|odds|return|yield|upside|downside|"
    r"change|changed|rose|fell|gain|loss|ratio|multiple|rate|close|closing)\b|"
    r"\b(?:p/e|eps|revenue|market cap)\b|"
    r"가격|주가|종가|현재가|목표가|목표\s*주가|확률|수익률|상승률|하락률|변화|변동|"
    r"비율|배수|배\s*(?:상승|하락|수익)|상승|하락)"
    , re.IGNORECASE
)
_FORMULA_RE = re.compile(r"=\s*(?P<result>[-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?P<percent>%|퍼센트)", re.IGNORECASE)
_LONG_RE = re.compile(
    r"\b(?:you\s+(?:currently\s+)?(?:hold|own)\s+(?:(?:a|an)\s+)?long(?:\s+position)?|"
    r"your\s+long\s+position|you\s+are\s+long|currently\s+long|long\s+position\s+held)\b|"
    r"(?:롱|매수)\s*(?:포지션.{0,12})?보유|(?:롱|매수).{0,12}보유\s*중|"
    r"현재\s*(?:롱|매수)\s*(?:포지션|보유)|롱을\s*보유",
    re.IGNORECASE,
)
_SHORT_RE = re.compile(
    r"\b(?:you\s+(?:currently\s+)?(?:hold|own)\s+(?:(?:a|an)\s+)?short(?:\s+position)?|"
    r"your\s+short\s+position|you\s+are\s+short|currently\s+short|short\s+position\s+held)\b|"
    r"(?:숏|공매도)\s*(?:포지션.{0,12})?보유|(?:숏|공매도).{0,12}보유\s*중|"
    r"현재\s*(?:숏|공매도)\s*(?:포지션|보유)|숏을\s*보유",
    re.IGNORECASE,
)
_ANY_HOLD_RE = re.compile(
    r"\b(?:you\s+(?:currently\s+)?(?:hold|own|have)|your\s+(?:current|existing)\s+"
    r"(?:long\s+|short\s+)?position|(?:current|existing)\s+(?:long\s+|short\s+)?position)\b|"
    r"현재\s*(?:롱|숏|매수|공매도)?\s*포지션|기존\s*(?:롱|숏|매수|공매도)?\s*포지션|"
    r"(?:롱|숏|매수|공매도)\s*포지션.{0,12}보유|보유\s*중",
    re.IGNORECASE,
)
_FLAT_RE = re.compile(
    r"\b(?:no\s+(?:current\s+)?position|currently\s+flat|your\s+position\s+is\s+flat|"
    r"do\s+not\s+(?:currently\s+)?(?:hold|own)|not\s+currently\s+invested|no\s+shares)\b|"
    r"포지션이\s*없|보유하지\s*않|미보유|플랫\s*상태|무포지션",
    re.IGNORECASE,
)
_NEW_POSITION_RE = re.compile(
    r"\b(?:open|start|initiate|establish|enter)\s+(?:a\s+)?new\s+position\b|\bnew\s+entry\b|"
    r"(?:신규|새)\s*(?:롱|숏|매수|공매도)?\s*포지션|신규\s*진입|새로\s*진입",
    re.IGNORECASE,
)
_MANAGEMENT_RE = re.compile(
    r"\b(?:maintain|hold|reduce|trim|close|exit|liquidate)\s+(?:your|the)\s+"
    r"(?:(?:current|existing)\s+)?(?:long\s+|short\s+)?position\b|"
    r"(?:현재|기존|보유)\s*(?:롱|숏|매수|공매도)?\s*포지션.{0,16}(?:유지|축소|줄이|청산|정리)|"
    r"포지션을\s*(?:유지|축소|줄이|청산|정리)",
    re.IGNORECASE,
)
_CONDITIONAL_RE = re.compile(
    r"\b(?:if|assuming|should\s+you|in\s+the\s+event\s+that)\b|만약|라면|경우에는|경우라면",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QualityWarning:
    """One review candidate, identified by report location and reason."""

    location: str
    reason: str


def extract_numeric_values(text: str) -> list[str]:
    """Keep numeric tokens from a tool result without retaining its raw text."""
    return _NUMBER_RE.findall(text or "")


def _number(value: str) -> Decimal | None:
    try:
        number = Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _sentences(line: str):
    return (sentence.strip() for sentence in re.split(r"(?<!\d)[.!?。！？](?:\s+|$)", line) if sentence.strip())


def _expression_value(node):
    if isinstance(node, ast.Expression):
        return _expression_value(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value)), [Decimal(str(node.value))], False
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value, inputs, operated = _expression_value(node.operand)
        return (value if isinstance(node.op, ast.UAdd) else -value), inputs, operated
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left, left_inputs, _ = _expression_value(node.left)
        right, right_inputs, _ = _expression_value(node.right)
        if isinstance(node.op, ast.Add):
            value = left + right
        elif isinstance(node.op, ast.Sub):
            value = left - right
        elif isinstance(node.op, ast.Mult):
            value = left * right
        else:
            value = left / right
        return value, left_inputs + right_inputs, True
    raise ValueError("unsupported calculation")


def _supported_percent_calculation(sentence: str, evidence: set[Decimal]) -> bool:
    result_match = _FORMULA_RE.search(sentence)
    if not result_match:
        return False
    left = sentence[:result_match.start()]
    target = _number(result_match.group("result"))
    if target is None:
        return False
    # Find a short numeric expression immediately before '='; AST restricts it
    # to arithmetic and numeric literals, so report text is never evaluated.
    for start, char in enumerate(left):
        if char not in "0123456789(+-":
            continue
        expression = left[start:].strip().replace(",", "")
        try:
            value, inputs, operated = _expression_value(ast.parse(expression, mode="eval"))
        except (SyntaxError, ValueError, ZeroDivisionError, ArithmeticError):
            continue
        if operated and all(value in evidence for value in inputs) and value * 100 == target:
            return True
    return False


def _review_numeric_claims(parts, evidence_values: Sequence[str]) -> list[QualityWarning]:
    evidence = {number for value in evidence_values if (number := _number(str(value))) is not None}
    warnings = []
    for _heading, _folder, written in parts:
        for agent, _filename, report in written:
            for line_number, line in enumerate(str(report).splitlines(), 1):
                for sentence in _sentences(line):
                    numbers = [number for token in _NUMBER_RE.findall(sentence) if (number := _number(token)) is not None]
                    if not numbers or not _CLAIM_RE.search(sentence):
                        continue
                    if "=" in sentence:
                        supported = _supported_percent_calculation(sentence, evidence)
                    else:
                        supported = all(number in evidence for number in numbers)
                    if not supported:
                        rendered = ", ".join(str(number) for number in numbers)
                        warnings.append(QualityWarning(
                            f"{agent} · line {line_number}",
                            f"Numeric claim candidate ({rendered}) has no matching supplied tool value or supported calculation.",
                        ))
    return warnings


def _position_status(final_state: Mapping, ticker: str):
    if not final_state.get("portfolio_context_provided"):
        return None
    canonical = normalize_symbol(ticker)
    quantities = []
    for position in final_state.get("portfolio_positions") or ():
        if not isinstance(position, Mapping) or not position.get("ticker"):
            continue
        if normalize_symbol(str(position["ticker"])) == canonical:
            try:
                quantity = Decimal(str(position["quantity"]))
            except (InvalidOperation, KeyError, TypeError, ValueError):
                return None
            if not quantity.is_finite():
                return None
            quantities.append(quantity)
    quantity = sum(quantities, Decimal(0))
    return "long" if quantity > 0 else "short" if quantity < 0 else "flat"


def _review_holdings(parts, final_state: Mapping, ticker: str) -> list[QualityWarning]:
    status = _position_status(final_state, ticker)
    warnings = []
    for _heading, _folder, written in parts:
        for agent, _filename, report in written:
            if agent not in {"Trader", "Portfolio Manager"}:
                continue
            for line_number, line in enumerate(str(report).splitlines(), 1):
                for sentence in _sentences(line):
                    if _CONDITIONAL_RE.search(sentence):
                        continue
                    long_claim = bool(_LONG_RE.search(sentence))
                    short_claim = bool(_SHORT_RE.search(sentence))
                    holding_claim = long_claim or short_claim or bool(_ANY_HOLD_RE.search(sentence))
                    flat_claim = bool(_FLAT_RE.search(sentence))
                    new_position = bool(_NEW_POSITION_RE.search(sentence))
                    existing_management = bool(_MANAGEMENT_RE.search(sentence))
                    reason = None
                    if status is None and holding_claim:
                        reason = "An explicit holding claim cannot be checked because portfolio status was not provided."
                    elif status == "flat" and ((holding_claim and not flat_claim) or existing_management):
                        reason = "The text assumes an existing position, while the provided portfolio is flat."
                    elif status in {"long", "short"} and (flat_claim or new_position):
                        reason = f"The text assumes no current position, while the provided portfolio is {status}."
                    elif status == "long" and short_claim:
                        reason = "The text claims a short holding, while the provided portfolio is long."
                    elif status == "short" and long_claim:
                        reason = "The text claims a long holding, while the provided portfolio is short."
                    if reason:
                        warnings.append(QualityWarning(f"{agent} · line {line_number}", reason))
    return warnings


def review_output(final_state: Mapping, ticker: str, parts) -> tuple[QualityWarning, ...]:
    """Return stable numeric and direct-holdings warnings without changing text."""
    warnings = _review_numeric_claims(parts, final_state.get("tool_evidence_numbers") or ())
    warnings.extend(_review_holdings(parts, final_state, ticker))
    return tuple(warnings)
