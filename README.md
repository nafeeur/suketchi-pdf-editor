![PDF Editor Banner](https://github.com/user-attachments/assets/5a1e1c6c-ddd3-420a-905c-af647978de5d)

## A lightweight, free, and open-source PDF reader and editor.

Suketchi PDF delivers a smooth, native desktop experience for viewing, navigating, and editing PDF documents without heavy resource overhead.

---

## Screenshots

<img width="2304" height="1456" alt="s1" src="https://github.com/user-attachments/assets/2fe7ef51-ae56-45af-90b9-323ad6be93b2" />

![Application Interface](https://github.com/user-attachments/assets/d4986ff7-f3a2-4d9c-9120-5e57a31aca70)

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

This project is licensed under the GPL-3.0 License. See the LICENSE file in the root directory for more details.
