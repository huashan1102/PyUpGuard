class ShareData():
    name_base_global_search_record = []

class LanguageParams():
    """
    Shallow structure to make storing language-specific parameters cleaner
    """
    def __init__(self, source_type='script', ruby_version='27'):
        self.source_type = source_type
        self.ruby_version = ruby_version

class ShareFlag():
    analyzing_from_outside = True

def djoin(*tup):
    if len(tup) == 1 and isinstance(tup[0], list):
        tup = tup[0]
    return '.'.join(filter(None, tup))


def flatten(list_of_lists):
    return [el for sublist in list_of_lists for el in sublist]

class Namespace(dict):
    def __init__(self, *args, **kwargs):
        d = {k: k for k in args}
        d.update(dict(kwargs.items()))
        super().__init__(d)

    def __getattr__(self, item):
        return self[item]


OWNER_CONST = Namespace("UNKNOWN_VAR", "UNKNOWN_MODULE")
GROUP_TYPE = Namespace("FILE", "CLASS", "NAMESPACE")