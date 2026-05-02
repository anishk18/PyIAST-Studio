from __future__ import annotations

import io
from typing import Any, Literal

import numpy as np
import pandas as pd
import pyiast
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator


ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "frontend"

app = FastAPI(
    title="pyIAST Studio",
    description="A browser front end for fitting pure-component isotherms and running IAST calculations.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DataPoint(BaseModel):
    pressure: float = Field(ge=0)
    loading: float = Field(ge=0)


class ComponentInput(BaseModel):
    name: str = Field(min_length=1)
    method: Literal["model", "interpolator"] = "model"
    model: str = "Langmuir"
    fill_value: float | None = None
    data: list[DataPoint] = Field(min_length=2)


class ForwardRequest(BaseModel):
    components: list[ComponentInput] = Field(min_length=2)
    total_pressure: float = Field(gt=0)
    gas_fractions: list[float]
    verbose: bool = False

    @model_validator(mode="after")
    def validate_fractions(self) -> "ForwardRequest":
        if len(self.components) != len(self.gas_fractions):
            raise ValueError("gas_fractions must match the number of components")
        if any(value < 0 for value in self.gas_fractions):
            raise ValueError("gas_fractions must be non-negative")
        total = sum(self.gas_fractions)
        if not np.isclose(total, 1.0, atol=1e-6):
            raise ValueError("gas_fractions must sum to 1")
        return self


class ReverseRequest(BaseModel):
    components: list[ComponentInput] = Field(min_length=2)
    total_pressure: float = Field(gt=0)
    adsorbed_fractions: list[float]

    @model_validator(mode="after")
    def validate_fractions(self) -> "ReverseRequest":
        if len(self.components) != len(self.adsorbed_fractions):
            raise ValueError("adsorbed_fractions must match the number of components")
        if any(value < 0 for value in self.adsorbed_fractions):
            raise ValueError("adsorbed_fractions must be non-negative")
        total = sum(self.adsorbed_fractions)
        if not np.isclose(total, 1.0, atol=1e-6):
            raise ValueError("adsorbed_fractions must sum to 1")
        return self


def dataframe_from_points(component: ComponentInput) -> pd.DataFrame:
    points = sorted(component.data, key=lambda point: point.pressure)
    return pd.DataFrame(
        {
            "Pressure": [point.pressure for point in points],
            "Loading": [point.loading for point in points],
        }
    )


def make_isotherm(component: ComponentInput):
    frame = dataframe_from_points(component)
    try:
        if component.method == "interpolator":
            kwargs: dict[str, Any] = {}
            if component.fill_value is not None:
                kwargs["fill_value"] = component.fill_value
            return pyiast.InterpolatorIsotherm(
                frame,
                pressure_key="Pressure",
                loading_key="Loading",
                **kwargs,
            )

        return pyiast.ModelIsotherm(
            frame,
            pressure_key="Pressure",
            loading_key="Loading",
            model=component.model,
        )
    except Exception as exc:  # pyIAST raises plain exceptions for some fit failures.
        raise HTTPException(status_code=422, detail=f"{component.name}: {exc}") from exc


def component_fit_summary(component: ComponentInput, isotherm: Any) -> dict[str, Any]:
    frame = dataframe_from_points(component)
    max_pressure = float(frame["Pressure"].max())
    preview_pressures = np.linspace(0, max_pressure, 24)
    return {
        "name": component.name,
        "method": component.method,
        "model": component.model if component.method == "model" else "Interpolator",
        "params": getattr(isotherm, "params", {}),
        "data": frame.to_dict(orient="records"),
        "fit": [
            {
                "pressure": float(pressure),
                "loading": float(isotherm.loading(float(pressure))),
            }
            for pressure in preview_pressures
        ],
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/parse-csv")
async def parse_csv(file: UploadFile) -> dict[str, Any]:
    raw = await file.read()
    try:
        frame = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc
    return {
        "columns": list(frame.columns),
        "rows": frame.replace({np.nan: None}).to_dict(orient="records"),
    }


@app.get("/api/models")
def models() -> dict[str, list[str]]:
    return {"models": list(getattr(pyiast, "_MODELS", []))}


@app.post("/api/iast")
def run_iast(request: ForwardRequest) -> dict[str, Any]:
    isotherms = [make_isotherm(component) for component in request.components]
    partial_pressures = request.total_pressure * np.array(request.gas_fractions)
    try:
        loadings = pyiast.iast(
            partial_pressures,
            isotherms,
            verboseflag=request.verbose,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    total_loading = float(np.sum(loadings))
    adsorbed_fractions = (loadings / total_loading).tolist() if total_loading else [0] * len(loadings)
    return {
        "mode": "forward",
        "partial_pressures": partial_pressures.tolist(),
        "components": [
            {
                "name": component.name,
                "gas_fraction": request.gas_fractions[index],
                "partial_pressure": float(partial_pressures[index]),
                "loading": float(loadings[index]),
                "adsorbed_fraction": float(adsorbed_fractions[index]),
            }
            for index, component in enumerate(request.components)
        ],
        "total_loading": total_loading,
        "fits": [
            component_fit_summary(component, isotherm)
            for component, isotherm in zip(request.components, isotherms)
        ],
    }


@app.post("/api/reverse-iast")
def run_reverse_iast(request: ReverseRequest) -> dict[str, Any]:
    isotherms = [make_isotherm(component) for component in request.components]
    try:
        gas_fractions, loadings = pyiast.reverse_iast(
            request.adsorbed_fractions,
            request.total_pressure,
            isotherms,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    partial_pressures = request.total_pressure * np.array(gas_fractions)
    return {
        "mode": "reverse",
        "components": [
            {
                "name": component.name,
                "adsorbed_fraction": request.adsorbed_fractions[index],
                "gas_fraction": float(gas_fractions[index]),
                "partial_pressure": float(partial_pressures[index]),
                "loading": float(loadings[index]),
            }
            for index, component in enumerate(request.components)
        ],
        "total_loading": float(np.sum(loadings)),
        "fits": [
            component_fit_summary(component, isotherm)
            for component, isotherm in zip(request.components, isotherms)
        ],
    }


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
