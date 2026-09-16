"""Small explicit Accept-Encoding negotiator for identity and gzip."""
import re


def qualities(value):
    if not value:
        return 0.0, 1.0
    choices = {}
    for item in value.lower().split(","):
        parts = [part.strip() for part in item.split(";")]
        coding = parts[0]
        quality = 1.0
        if len(parts) > 1:
            if len(parts) != 2 or not re.fullmatch(r"q=(?:0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?)", parts[1]):
                quality = 0.0
            else:
                quality = float(parts[1][2:])
        choices[coding] = quality
    gzip = choices.get("gzip", choices.get("*", 0.0))
    identity = choices.get("identity", 0.0 if choices.get("*") == 0 else 1.0)
    return gzip, identity
