import re


def normalize_phone(value):
    """Normalize a Nigerian phone number to E.164 format (+234XXXXXXXXXX).

    Accepted inputs (all normalize to +234 + 10 digits):
      +2348012345678  (14 chars), 2348012345678 (13 chars), 08012345678 (11 chars)

    Returns the normalized string or the original value unchanged
    if it cannot be interpreted (DB unique constraint catches problems).
    """
    if not value:
        return value

    cleaned = re.sub(r'[^\d+]', '', value)

    # Already in E.164 form: +234 + 10 digits
    if cleaned.startswith('+234') and len(cleaned) == 14:
        return cleaned

    # Country code without '+': 234 + 10 digits
    if cleaned.startswith('234') and len(cleaned) == 13:
        return '+' + cleaned

    # Local format: 0 + 10 digits
    if cleaned.startswith('0') and len(cleaned) == 11:
        return '+234' + cleaned[1:]

    # Fallback – let the DB constraint/caller handle invalid formats
    return cleaned
