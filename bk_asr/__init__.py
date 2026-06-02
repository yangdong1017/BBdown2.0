from .BcutASR import BcutASR
from .JianYingASR import JianYingASR
from .KuaiShouASR import KuaiShouASR

__all__ = ["BcutASR", "JianYingASR", "KuaiShouASR"]


def transcribe(audio_file, platform):
    assert platform in __all__
    asr = globals()[platform](audio_file)
    return asr.run()
