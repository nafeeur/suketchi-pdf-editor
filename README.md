![PDF Editor Banner](https://raw.githubusercontent.com/nafeeur/suketchi-pdf-editor/main/docs/screenshots/banner.jpg)

## A lightweight, free, and open-source PDF reader and editor.

Suketchi PDF delivers a smooth, native desktop experience for viewing, navigating, and editing PDF documents without heavy resource overhead.

---

## Screenshots

![Editing a PDF in Suketchi](https://raw.githubusercontent.com/nafeeur/suketchi-pdf-editor/main/docs/screenshots/screenshot1.jpg)

![Suketchi tools panel](https://raw.githubusercontent.com/nafeeur/suketchi-pdf-editor/main/docs/screenshots/screenshot2.jpg)

![Suketchi page view](https://raw.githubusercontent.com/nafeeur/suketchi-pdf-editor/main/docs/screenshots/screenshot3.jpg)

---

## Installation & Setup

### Prerequisites
* Python 3.10 or higher installed on your computer.

### Install from PyPI
It is highly recommended to isolate the install using a virtual environment:

* **Linux / macOS**:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```
* **Windows**:
  ```bash
  python -m venv venv
  venv\Scripts\activate
  ```

Then install with pip:
```bash
pip install --upgrade pip
pip install suketchi
```

Optional extras add support for spell checking, DOCX export, and cryptographic PDF signing:
```bash
pip install "suketchi[all]"
```

## Running the Application

Once installed, launch the editor with:
```bash
suketchi
```

The first time you run it, Suketchi automatically adds itself to your applications
menu (Linux), Start Menu (Windows), or Applications folder (macOS) with its icon,
so afterwards you can just launch it like any other installed app. (pip cannot run
this step during `pip install` itself — it happens on first launch instead.) To
add or refresh the shortcut manually, run:
```bash
suketchi --install-shortcut
```

### Running from source
```bash
git clone https://github.com/nafeeur/suketchi-pdf-editor
cd suketchi-pdf-editor
pip install -e .
suketchi
```

---

## License

This project is licensed under the GPL-3.0 License. See the LICENSE for more details.
