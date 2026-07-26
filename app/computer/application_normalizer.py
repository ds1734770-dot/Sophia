import re
class ApplicationNormalizer:

    def normalize(self, name):

        name = name.lower()

        name = re.sub(r"[^\w\s]", "", name)

        name = re.sub(r"\s+", " ", name)

        return name.strip()

    def aliases(self, name):

        aliases = set()
    
        normalized = self.normalize(name)
    
        aliases.add(normalized)
    
        words = normalized.split()
    
        if len(words) > 1:
        
            aliases.add("".join(words))
    
        return list(aliases)