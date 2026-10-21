# Introduction

This repository is the repository of our team (MYA) for the competition **More than a Hack 2027**.

The Team is composed of : 
- Ali ABOUHACHIM-ALAMI
- Youssef BENADDI
- Maxime BENDAVID

## Environment Setup

Follow these steps to set up the development environment and run the notebooks and scripts.

### 1. Create a virtual environment

From the repository root, create a virtual environment named `.venv`:

```bash
python3 -m venv .venv
```

### 2. Activate the virtual environment

- **Linux / macOS:**
  ```bash
  source .venv/bin/activate
  ```
- **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate.bat
  ```

### 3. Install required packages

Make sure your virtual environment is activated, then install the dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Running Jupyter Notebooks

When opening notebooks (such as `data_exploration.ipynb`) in VS Code or your IDE:
1. Click on **Select Kernel** in the top-right corner of the notebook.
2. Choose **Python Environments...**.
3. Select the `.venv` kernel (`.venv/bin/python`).
