![PDF Editor Banner](https://github.com/user-attachments/assets/5a1e1c6c-ddd3-420a-905c-af647978de5d)

## A lightweight, free, and open-source PDF reader and editor.

Suketchi PDF delivers a smooth, native desktop experience for viewing, navigating, and editing PDF documents without heavy resource overhead.

---

## Screenshots

<img width="2165" height="1393" alt="Screenshot_20260817_221032-1" src="https://github.com/user-attachments/assets/d9315c51-d618-4fad-98be-08df1bb9670b" />
<img width="2163" height="1398" alt="2" src="https://github.com/user-attachments/assets/e070ba20-67fb-4e44-9a1f-d8a5c760a0a9" />
<img width="2370" height="1596" alt="Screenshot_20260817_221817" src="https://github.com/user-attachments/assets/553611dd-da63-40dd-b8f9-98f17db8f412" />

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
