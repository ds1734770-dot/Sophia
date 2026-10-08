class ConfidenceEvaluator:

    MIN_SCORE = 75

    MIN_MARGIN = 10

    # -----------------------------------------

    def confident(self, matches):

        if not matches:
            return False

        best = matches[0]

        if best.score < self.MIN_SCORE:
            return False

        if len(matches) == 1:
            return True

        second = matches[1]

        return (best.score - second.score) >= self.MIN_MARGIN