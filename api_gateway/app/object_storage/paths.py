class BucketFuzzers:

    """S3 paths for 'fuzzers' bucket"""

    def __init__(self, name: str):
        self.name = name

    def binaries(self, fuzzer_id, fuzzer_rev, ext=".tar.gz"):
        return self.name, f"{fuzzer_id}/{fuzzer_rev}/binaries{ext}"

    def seeds(self, fuzzer_id, fuzzer_rev, ext=".tar.gz"):
        return self.name, f"{fuzzer_id}/{fuzzer_rev}/seeds{ext}"

    def config(self, fuzzer_id, fuzzer_rev, ext=".json"):
        return self.name, f"{fuzzer_id}/{fuzzer_rev}/config{ext}"

    def fuzzer_dir(self, fuzzer_id):
        return self.name, fuzzer_id

    def revision_dir(self, fuzzer_id, fuzzer_rev):
        return self.name, f"{fuzzer_id}/{fuzzer_rev}"


class BucketData:

    """S3 paths for 'data' bucket"""

    def __init__(self, name: str):
        self.name = name

    def merged_corpus(self, fuzzer_id, fuzzer_rev, ext=".tar.gz"):
        return self.name, f"{fuzzer_id}/{fuzzer_rev}/corpus/corpus{ext}"

    def logs(self, fuzzer_id, fuzzer_rev, result_id, ext=".gz"):
        return self.name, f"{fuzzer_id}/{fuzzer_rev}/logs/{result_id}{ext}"

    def crash(self, fuzzer_id, fuzzer_rev, input_id, ext=".bin"):
        return self.name, f"{fuzzer_id}/{fuzzer_rev}/crashes/{input_id}{ext}"

    def fuzzer_dir(self, fuzzer_id):
        return self.name, fuzzer_id

    def revision_dir(self, fuzzer_id, fuzzer_rev):
        return self.name, f"{fuzzer_id}/{fuzzer_rev}"
