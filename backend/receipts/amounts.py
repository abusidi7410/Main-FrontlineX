"""Money-to-words for the receipt's legal amount line."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

ONES = (
    'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
    'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen',
    'sixteen', 'seventeen', 'eighteen', 'nineteen',
)
TENS = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety')
SCALES = ((1_000_000_000, 'billion'), (1_000_000, 'million'), (1_000, 'thousand'))


def _under_hundred(number: int) -> str:
    if number < 20:
        return ONES[number]
    head, tail = divmod(number, 10)
    return TENS[head] + (f'-{ONES[tail]}' if tail else '')


def _under_thousand(number: int) -> str:
    hundreds, remainder = divmod(number, 100)
    parts = []
    if hundreds:
        parts.append(f'{ONES[hundreds]} hundred')
    if remainder:
        parts.append(_under_hundred(remainder))
    return ' and '.join(parts)


def integer_to_words(number: int) -> str:
    if number == 0:
        return 'zero'
    chunks = []
    remaining = number
    for scale, label in SCALES:
        value, remaining = divmod(remaining, scale)
        if value:
            chunks.append(f'{integer_to_words(value)} {label}')
    if remaining:
        chunks.append(_under_thousand(remaining))
    return ' '.join(chunks)


def amount_in_words(amount) -> str:
    """``115000`` → ``One hundred and fifteen thousand naira only``.

    Kobo is included when non-zero, because a receipt must state the exact
    amount it acknowledges — rounding it away in words would make the words
    disagree with the figures.
    """
    value = Decimal(str(amount or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    naira = int(value)
    kobo = int((value - naira) * 100)
    words = integer_to_words(naira)
    text = f'{words} naira'
    if kobo:
        text += f' and {integer_to_words(kobo)} kobo'
    return text[:1].upper() + text[1:] + ' only'
