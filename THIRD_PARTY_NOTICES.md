# Third-party notices

The project code is MIT licensed. This source repository does not contain
dependency wheels, Qt libraries, model weights, downloaded runtime source trees,
Apple frameworks or a compiled recording helper. A requirements entry is not
a relicensing of the dependency. License texts retained under `third_party/`
apply to the named optional upstream components, not the entire project.

## Python dependencies

These identifiers reflect the installed distribution metadata for the pinned
verification environment. Distributed wheels can bundle additional components
with their own notices; retain their upstream license files when redistributing
those wheels or creating a binary application.

| Dependency | Version | Reported license |
| --- | --- | --- |
| PySide6 Essentials / shiboken6 | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; Qt commercial licensing is also available separately |
| certifi | 2026.7.22 | MPL-2.0 |
| cryptography | 49.0.0 | Apache-2.0 OR BSD-3-Clause |
| NumPy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; bundled numerical libraries have notices |
| opencv-python-headless | 4.14.0.94 | Apache 2.0; bundled third-party components have notices |
| cffi / pycparser | 2.1.1 / 3.0 | MIT-0 / BSD-3-Clause |
| pytest / pluggy / iniconfig | 9.1.1 / 1.6.0 / 2.3.0 | MIT |
| mypy / mypy_extensions / librt | 1.20.2 / 1.1.0 / 0.16.0 | MIT |
| Ruff / setuptools | 0.16.10 / 84.0.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pathspec | 1.1.1 | MPL-2.0 |
| Pygments | 2.21.0 | BSD-2-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |

## Qt/PySide distribution

The app uses PySide6 and Qt Quick. PySide/Qt are **not MIT licensed**.
The source-only, dynamically imported application can use the LGPL option for
eligible Qt modules, subject to that license. This repository makes no claim
that a future standalone bundle automatically satisfies it.

Before distributing Qt/PySide binaries, preserve applicable copyright and
third-party notices, supply the LGPL/GPL license texts as applicable, provide
the required corresponding library source or valid source offer, and preserve
the user's ability to modify, replace/relink and run the libraries. Static
linking, restricted application stores, signing and installation restrictions
need a separate review. Some Qt modules are GPL-only; adding them changes the
licensing assessment. Project MIT licensing does not remove these obligations.

Official references:

- [Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations)
- [Qt for Python licenses and bundled notices](https://doc.qt.io/qtforpython-6/licenses.html)
- [Qt licensing](https://doc.qt.io/qt-6/licensing.html)

## Optional tools and models

- **whisper.cpp**: ggml authors, MIT. The retained upstream license is
  [`third_party/whisper.cpp-LICENSE.txt`](third_party/whisper.cpp-LICENSE.txt).
  Its downloaded source/binaries are excluded. OpenAI Whisper model weights
  have their own [upstream MIT license](https://github.com/openai/whisper/blob/main/LICENSE).
- **YuNet**: Shiqi Yu and upstream contributors, MIT. Retained license:
  [`third_party/YuNet-LICENSE.txt`](third_party/YuNet-LICENSE.txt).
- **SFace**: upstream OpenCV Zoo model, Apache-2.0. Retained license:
  [`third_party/SFace-LICENSE.txt`](third_party/SFace-LICENSE.txt).
- **Ollama**: optional external runtime; obtain it from the
  [official project](https://github.com/ollama/ollama) and preserve its MIT and
  bundled-component notices if redistributing it. No Ollama application is included.
- **Gemma 3 and EmbeddingGemma**: Google model terms, not the project MIT license.
  [Gemma Terms](https://ai.google.dev/gemma/terms) include use and redistribution
  conditions. No weights or model derivatives are included. Users must review
  current terms themselves before downloading. EmbeddingGemma is not installed
  or required by this source release.
- **Apple components**: macOS AVFoundation/AppKit, Keychain tools, system speech
  and installed voices remain Apple components; the repository includes only
  project-authored helper source and invokes system facilities.

Pinned model references, hashes and license links are in
[`docs/models.json`](docs/models.json). Upstream terms govern optional downloads.

## Project artwork

The PNG/ICNS branding assets were created for Miwl 2 with AI assistance and are
included with the project. No third-party font files or stock images are
distributed. The license conveys only rights the project can grant, and does
not grant rights to another party's trademarks or imply upstream endorsement.
