# Optional local runtimes

The fixture writing provider and default test suite work without models.
This repository contains installer references, **not model weights or runtime
binaries**. Review each upstream license/current terms before downloading;
the source MIT license does not grant rights to those downloads.
Provenance and expected hashes are in [models.json](models.json).

## Ollama / Gemma

Obtain Ollama from [ollama.com](https://ollama.com/download). After reviewing
the current [Gemma Terms](https://ai.google.dev/gemma/terms), you can install
`gemma3:4b` with your own Ollama installation and configure Miwl's local
provider at `http://127.0.0.1:11434`. The checked reference was Gemma 3 4B
Q4_K_M, approximately 3.34 GB. The manifest digest in `models.json` records
that verification environment; the remote model tag can change and the app
does not pin a tag to that digest automatically.

Keep Ollama local. `tools/start_local_runtime.sh` sets loopback listening,
project-local model storage, cloud disabled, one parallel job and 4096 context,
but expects `.runtime/Ollama.app` to exist. It does not install Ollama or fetch
models. A normal system Ollama installation can be configured separately.

EmbeddingGemma is not included, installed or needed. This release does not
provide semantic embedding retrieval, and does not accept new model terms
on the user's behalf.

## whisper.cpp / local voice

Use the pinned upstream source revision with CMake and Apple's Command Line
Tools already installed:

```sh
mkdir -p .runtime
git clone https://github.com/ggml-org/whisper.cpp.git .runtime/whisper.cpp
git -C .runtime/whisper.cpp checkout 60c0be6ac8fa71b1a2ae2dd938a31a34a508e774
cmake -S .runtime/whisper.cpp -B .runtime/whisper.cpp/build -DGGML_METAL=ON
cmake --build .runtime/whisper.cpp/build --config Release -j 4
```

Review the upstream licenses, then obtain `ggml-base.bin` from the model source
listed in `models.json` and place it at
`.runtime/whisper.cpp/models/ggml-base.bin`. Verify its SHA-256 before use:

```sh
shasum -a 256 .runtime/whisper.cpp/models/ggml-base.bin
```

Expected hash:
`60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe`.
The current voice loader checks file availability; this manual hash check is
part of optional setup, not an enforced loader check.

For explicit Mac recording, build the project-authored helper:

```sh
sh tools/build_voice_helper.sh
```

It creates a local ad-hoc-signed `.runtime/MiwlVoice.app`; it is not a distributed
or notarized application. macOS asks for microphone access when Record is
chosen. Importing WAV works without opening a microphone. The app uses four
CPU threads for ASR by default. System speech playback uses `/usr/bin/say`;
no voice files are distributed.

## Optional YuNet / SFace

Review the retained MIT/Apache-2.0 licenses and pinned OpenCV Zoo provenance
in `models.json`. Obtain the two referenced ONNX files from their exact upstream
URLs and place them in `.runtime/vision-models/`:

- `face_detection_yunet_2023mar.onnx`
- `face_recognition_sface_2021dec.onnx`

Verify both SHA-256 values against `models.json`. Unlike the voice loader,
the vision loader checks these pinned hashes before inference. Models missing
or differing from these hashes are rejected. No face profiles or real images
are included in this repository. Read the consent and uncertainty boundaries
in [PRIVACY_AND_SAFETY.md](PRIVACY_AND_SAFETY.md) before enabling matching.

## Redistribution

Do not commit downloaded files to this repository. If you later distribute
runtimes or models, satisfy their license/terms, attribution, notice and source
requirements separately. Gemma redistribution has additional restrictions;
no Gemma weights or derivatives are part of this source release.
