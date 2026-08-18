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

### 1. Clone the Repository
```bash
git clone https://github.com/nafeeur/suketchi-pdf-editor
cd suketchi-pdf-editor
```

### 2. Set Up a Virtual Environment
It is highly recommended to isolate your project dependencies using a virtual environment:

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

### 3. Install Required Dependencies
Upgrade pip and install the core GUI and rendering engine packages:
```bash
pip install --upgrade pip
pip install PyQt6 PyMuPDF
```

## Running the Application

Once your virtual environment is active and dependencies are fully installed, launch the editor:
```bash
python suketchi_pdf.py
```

---

## License

This project is licensed under the GPL-3.0 License. See the LICENSE for more details.
