import re

class DataNormalizer:
    @staticmethod
    def normalize_is_number(raw_number: str) -> str:
        """
        Normalizes variations of IS standard numbers into a canonical format.
        Examples:
          "is 456-2000" -> "IS 456:2000"
          "IS:456:2000" -> "IS 456:2000"
          "IS 1786/2008" -> "IS 1786:2008"
          "is456"       -> "IS 456"
        """
        if not raw_number:
            return ""

        clean = raw_number.strip().upper()
        # Replace common separators with single colon before year
        clean = re.sub(r'[\/:\-]\s*(\d{4})', r':\1', clean)
        # Ensure space after IS
        clean = re.sub(r'^IS\s*', 'IS ', clean)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()

    @staticmethod
    def clean_text(text: str) -> str:
        """Strip whitespace and collapse multiple spaces."""
        if not text:
            return ""
        return " ".join(text.split())
