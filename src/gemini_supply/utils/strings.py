def slugify(value: str) -> str:
  lowered = value.lower()
  chars: list[str] = []
  prev_hyphen = False
  for ch in lowered:
    if ch.isalnum():
      chars.append(ch)
      prev_hyphen = False
    else:
      if not prev_hyphen:
        chars.append("-")
        prev_hyphen = True
  slug = "".join(chars).strip("-")
  return slug or "item"


def trim(value: str | None) -> str | None:
  if value is None:
    return None
  trimmed = value.strip()
  if not trimmed:
    return None
  return trimmed
