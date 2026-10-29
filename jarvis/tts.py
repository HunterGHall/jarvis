"""Built-in text-to-speech: the OmniVoice model run in-process, speaking in a cloned voice.

Voices are looked for in your voices folder (see jarvis.paths) and then in the ones bundled with Jarvis.

A voice is either <name>.pt (a saved clone prompt) or <name>.mp3 + <name>.txt (a 3-10 s clip and what it says).
"""
import os
import sys
import threading
from pathlib import Path

from jarvis.paths import VOICES_DIR

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
VOICE_FOLDERS = [VOICES_DIR, ASSETS]  # yours first, so you can replace a bundled voice
CHECKPOINT = "k2-fsa/OmniVoice"
# VoiceStudio's model download, reused when present so nothing is fetched twice
_EXISTING_CACHE = Path(os.environ.get("LOCALAPPDATA", "")) / "OmniVoice" / "hf_cache"

_model = None
_prompts = {}
_lock = threading.Lock()


def _quiet():
    """Keeps model loading from printing progress bars and torch notes into the chat."""
    import logging

    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    logging.getLogger("torch.distributed.elastic.multiprocessing.redirects").setLevel(logging.ERROR)


def _prepare_imports():
    _quiet()
    vendor = str(HERE / "vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    if (_EXISTING_CACHE / "models--k2-fsa--OmniVoice").is_dir():
        os.environ.setdefault("HF_HUB_CACHE", str(_EXISTING_CACHE))


def available():
    """Raises a readable error when the packages the built-in voice needs are missing."""
    _quiet()
    for name in ("torch", "torchaudio", "transformers", "pydub", "psutil", "soundfile"):
        try:
            __import__(name)
        except ImportError:
            raise RuntimeError(f"The built-in voice needs '{name}'. Reinstall Jarvis: pipx reinstall jarvis-assistant")


def on_gpu():
    return _model is not None and next(_model.parameters()).device.type == "cuda"


def voices():
    names = set()
    for folder in VOICE_FOLDERS:
        names |= {path.stem for path in folder.glob("*.pt")} | {path.stem for path in folder.glob("*.mp3") if path.with_suffix(".txt").exists()}
    return sorted(names)


def _load():
    global _model
    if _model is None:
        _prepare_imports()
        import torch
        from omnivoice import OmniVoice
        from transformers.utils import logging as hf_logging

        hf_logging.disable_progress_bar()

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = OmniVoice.from_pretrained(
            CHECKPOINT, device_map=device, dtype=torch.float16 if device == "cuda" else torch.float32, load_asr=False
        )
    return _model


def _prompt(model, voice):
    if voice not in _prompts:
        saved, clip = next(((folder / f"{voice}.pt", folder / f"{voice}.mp3") for folder in VOICE_FOLDERS if (folder / f"{voice}.pt").exists() or (folder / f"{voice}.mp3").exists()), (None, None))
        script = clip.with_suffix(".txt") if clip else None
        if saved and saved.exists():
            from omnivoice.models.omnivoice import VoiceClonePrompt

            _prompts[voice] = VoiceClonePrompt.load(str(saved))
        elif clip and clip.exists() and script.exists():
            _prompts[voice] = model.create_voice_clone_prompt(str(clip), script.read_text(encoding="utf-8").strip())
        else:
            raise RuntimeError(f"No voice '{voice}'. Available: {', '.join(voices()) or 'none'}. Add them to {VOICES_DIR}.")
    return _prompts[voice]


def synthesize(text, s):
    """Returns (samples shaped (n, 1) float32, sample rate) for `text` using settings dict `s`."""
    import numpy as np
    import torch

    with _lock:
        model = _load()
        if s.get("seed") is not None:
            torch.manual_seed(int(s["seed"]))
        options = {
            key: s[key]
            for key in ("language", "instruct", "num_step", "guidance_scale", "t_shift", "layer_penalty_factor",
                        "position_temperature", "class_temperature", "denoise", "postprocess_output")
            if s.get(key) is not None
        }
        audio = model.generate(text=text, voice_clone_prompt=_prompt(model, s["voice"]), speed=s.get("speed"), **options)[0]
        rate = int(model.audio_tokenizer.config.sample_rate)
    if s.get("effect_preset"):
        from audio_dsp import apply_effects_chain, get_effect_chain

        try:
            audio = apply_effects_chain(audio, rate, get_effect_chain(s["effect_preset"]))
        except Exception:
            pass  # unprocessed audio is better than none
    samples = audio.detach().cpu().float().numpy().reshape(-1, 1)
    return np.clip(samples, -1.0, 1.0).astype(np.float32), rate
