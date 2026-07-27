from rapidfuzz import fuzz


class Scorer:

    EXACT_SCORE = 100
    ALIAS_SCORE = 90
    STARTS_WITH_SCORE = 70
    CONTAINS_SCORE = 50

    @staticmethod
    def fuzzy(query, text):

        return max(
            fuzz.ratio(query, text),
            fuzz.partial_ratio(query, text),
            fuzz.token_sort_ratio(query, text),
            fuzz.token_set_ratio(query, text),
        )