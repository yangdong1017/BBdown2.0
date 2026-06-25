from .BcutASR import BcutASR

__all__ = ["BcutASR"]


def transcribe(audio_file, platform):
    assert platform in __all__
    asr = globals()[platform](audio_file)
    return asr.run()
