from enum import Enum


class SubmissionStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    success = "success"
    failure = "failure"


class JobStatus(str, Enum):
    queued = "queued"
    solving = "solving"
    success = "success"
    failure = "failure"


class ArtifactType(str, Enum):
    wcs = "wcs"
    new_fits = "new_fits"
    corr = "corr"
    kml = "kml"
    annotated = "annotated"
