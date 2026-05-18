# pyIAST Studio

A small browser app for fitting pure-component adsorption isotherms and running
forward or reverse IAST calculations through
[pyIAST](https://github.com/CorySimon/pyIAST).

The app uses a FastAPI backend for the Python package and a build-free static
frontend, so there is no Node/npm step.

# Web Link for App on Streamlit
https://pyiast-studio-ark.streamlit.app/



## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

## Run with Streamlit

```powershell
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```


## What it does

- Edit or import pure-component pressure/loading data.
- Choose `ModelIsotherm` or `InterpolatorIsotherm` per component.
- Select any analytical model exposed by `pyiast._MODELS`.
- Run forward IAST from gas mole fractions and total pressure.
- Run reverse IAST from adsorbed mole fractions and total pressure.
- Preview fitted isotherms, component loadings, mole fractions, and fit
  parameters.

CSV import looks for column names containing `pressure` or `p`, and `loading`,
`uptake`, or `q`.
