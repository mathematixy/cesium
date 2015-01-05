from ..FeatureExtractor import ContextFeatureExtractor

class sdss_nearest_obj_type(ContextFeatureExtractor):
    """What is classification of the nearest object?"""
    active = True
    extname = 'sdss_nearest_obj_type' #extractor's name
    light_cutoff = 0.2 ## dont report anything farther away than this in arcmin

    verbose = False
    def extract(self):
        n = self.fetch_extr('intersdss')

        if n is None:
            if self.verbose:
                print("Nothing in the sdss extractor")
            return None

        if "in_footprint" not in n:
            if self.verbose:
                print("No footprint info in the sdss extractor. Should never happen.")
            return None

        if not n['in_footprint']:
            if self.verbose:
                print("Not in the footprint")
            return None

        if "type" not in n:
            if self.verbose:
                print("Desired parameter was not determined")
            return None

        if "dist_in_arcmin" not in n:
            if self.verbose:
                print("Desired parameter was not determined")
            return None

        if n["dist_in_arcmin"] > self.light_cutoff:
            return None
        else:
            rez = n["type"]
        if self.verbose:
            print(n)
        return rez
