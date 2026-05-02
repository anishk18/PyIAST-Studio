from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyiast
import streamlit as st


MODELS = list(getattr(pyiast, "_MODELS", ["Langmuir", "Quadratic", "BET", "Henry"]))


@dataclass
class Component:
    name: str
    method: str
    model: str
    fill_value: float | None
    data: pd.DataFrame


def default_components() -> list[dict[str, Any]]:
    return [
        {
            "name": "Ethane",
            "method": "Model fit",
            "model": "Langmuir",
            "fill_value": None,
            "data": pd.DataFrame(
                {
                    "Pressure": [1.0, 5.0, 15.0, 35.0, 65.0],
                    "Loading": [1.72, 6.8, 13.2, 20.8, 27.4],
                }
            ),
        },
        {
            "name": "Methane",
            "method": "Model fit",
            "model": "Langmuir",
            "fill_value": None,
            "data": pd.DataFrame(
                {
                    "Pressure": [1.0, 5.0, 15.0, 35.0, 65.0],
                    "Loading": [0.61, 2.85, 6.9, 10.9, 13.7],
                }
            ),
        },
    ]


def init_state() -> None:
    if "components" not in st.session_state:
        st.session_state.components = default_components()
    if "fractions" not in st.session_state:
        st.session_state.fractions = [0.05, 0.95]


def normalize_fractions(values: list[float], count: int) -> list[float]:
    padded = (values + [0.0] * count)[:count]
    total = sum(max(0.0, value) for value in padded)
    if total == 0:
        return [1 / count] * count
    return [max(0.0, value) / total for value in padded]


def clean_data(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.rename(columns=lambda column: str(column).strip())
    if "Pressure" not in data.columns or "Loading" not in data.columns:
        lower_to_original = {column.lower(): column for column in data.columns}
        pressure_column = next(
            (column for key, column in lower_to_original.items() if "pressure" in key or key == "p"),
            None,
        )
        loading_column = next(
            (
                column
                for key, column in lower_to_original.items()
                if "loading" in key or "uptake" in key or key == "q"
            ),
            None,
        )
        if pressure_column and loading_column:
            data = data.rename(columns={pressure_column: "Pressure", loading_column: "Loading"})

    data = data[["Pressure", "Loading"]].copy()
    data["Pressure"] = pd.to_numeric(data["Pressure"], errors="coerce")
    data["Loading"] = pd.to_numeric(data["Loading"], errors="coerce")
    data = data.dropna().sort_values("Pressure").reset_index(drop=True)
    return data


def build_isotherm(component: Component):
    data = clean_data(component.data)
    if len(data) < 2:
        raise ValueError(f"{component.name} needs at least two valid pressure/loading rows.")

    if component.method == "Interpolator":
        kwargs: dict[str, Any] = {}
        if component.fill_value is not None:
            kwargs["fill_value"] = component.fill_value
        return pyiast.InterpolatorIsotherm(
            data,
            pressure_key="Pressure",
            loading_key="Loading",
            **kwargs,
        )

    return pyiast.ModelIsotherm(
        data,
        pressure_key="Pressure",
        loading_key="Loading",
        model=component.model,
    )


def render_component_editor(index: int, item: dict[str, Any]) -> Component:
    with st.container(border=True):
        title_cols = st.columns([0.72, 0.28])
        with title_cols[0]:
            name = st.text_input("Component name", value=item["name"], key=f"name_{index}")
        with title_cols[1]:
            method = st.selectbox(
                "Method",
                ["Model fit", "Interpolator"],
                index=["Model fit", "Interpolator"].index(item["method"]),
                key=f"method_{index}",
            )

        model_cols = st.columns([0.6, 0.4])
        with model_cols[0]:
            model = st.selectbox(
                "Model",
                MODELS,
                index=MODELS.index(item["model"]) if item["model"] in MODELS else 0,
                disabled=method == "Interpolator",
                key=f"model_{index}",
            )
        with model_cols[1]:
            fill_value = st.number_input(
                "Interpolator fill value",
                min_value=0.0,
                value=float(item["fill_value"] or 0.0),
                step=0.01,
                disabled=method == "Model fit",
                key=f"fill_{index}",
            )

        uploaded = st.file_uploader(
            "CSV data",
            type=["csv"],
            key=f"upload_{index}",
            help="CSV should include pressure/loading columns.",
        )
        if uploaded is not None:
            item["data"] = clean_data(pd.read_csv(uploaded))

        edited = st.data_editor(
            item["data"],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Pressure": st.column_config.NumberColumn("Pressure", min_value=0.0, step=0.001),
                "Loading": st.column_config.NumberColumn("Loading", min_value=0.0, step=0.001),
            },
            key=f"data_{index}",
        )

        item.update(
            {
                "name": name,
                "method": method,
                "model": model,
                "fill_value": fill_value if method == "Interpolator" else None,
                "data": clean_data(edited),
            }
        )

    return Component(
        name=name,
        method="Interpolator" if method == "Interpolator" else "Model fit",
        model=model,
        fill_value=fill_value if method == "Interpolator" else None,
        data=clean_data(edited),
    )


def plot_isotherms(components: list[Component], isotherms: list[Any]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for component, isotherm in zip(components, isotherms):
        data = clean_data(component.data)
        ax.scatter(data["Pressure"], data["Loading"], label=f"{component.name} data", s=34)
        max_pressure = max(float(data["Pressure"].max()), 1.0)
        pressures = np.linspace(0, max_pressure, 80)
        loadings = [float(isotherm.loading(float(pressure))) for pressure in pressures]
        ax.plot(pressures, loadings, label=f"{component.name} fit", linewidth=2)

    ax.set_xlabel("Pressure")
    ax.set_ylabel("Loading")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    return fig


def parameter_rows(components: list[Component], isotherms: list[Any]) -> pd.DataFrame:
    rows = []
    for component, isotherm in zip(components, isotherms):
        params = getattr(isotherm, "params", {})
        rows.append(
            {
                "Component": component.name,
                "Model": component.model if component.method == "Model fit" else "Interpolator",
                "Parameters": ", ".join(f"{key}: {value:.6g}" for key, value in params.items()) or "n/a",
            }
        )
    return pd.DataFrame(rows)


def run_forward_iast(
    components: list[Component],
    isotherms: list[Any],
    total_pressure: float,
    fractions: list[float],
) -> pd.DataFrame:
    partial_pressures = total_pressure * np.array(fractions)
    loadings = pyiast.iast(partial_pressures, isotherms)
    total_loading = float(np.sum(loadings))
    adsorbed = loadings / total_loading if total_loading else np.zeros(len(loadings))
    return pd.DataFrame(
        {
            "Component": [component.name for component in components],
            "Gas fraction": fractions,
            "Partial pressure": partial_pressures,
            "Loading": loadings,
            "Adsorbed fraction": adsorbed,
        }
    )


def run_reverse_iast(
    components: list[Component],
    isotherms: list[Any],
    total_pressure: float,
    fractions: list[float],
) -> pd.DataFrame:
    gas_fractions, loadings = pyiast.reverse_iast(fractions, total_pressure, isotherms)
    return pd.DataFrame(
        {
            "Component": [component.name for component in components],
            "Adsorbed fraction": fractions,
            "Gas fraction": gas_fractions,
            "Partial pressure": total_pressure * np.array(gas_fractions),
            "Loading": loadings,
        }
    )


st.set_page_config(page_title="pyIAST Studio", layout="wide")
init_state()

st.title("pyIAST Studio")
st.caption("Fit pure-component isotherms and run forward or reverse IAST calculations.")

with st.sidebar:
    st.header("Mixture setup")
    mode = st.radio("Calculation", ["Forward IAST", "Reverse IAST"], horizontal=True)
    total_pressure = st.number_input("Total pressure", min_value=0.0001, value=65.0, step=1.0)

    st.divider()
    st.subheader("Components")
    count = st.number_input(
        "Number of components",
        min_value=2,
        max_value=5,
        value=len(st.session_state.components),
        step=1,
    )
    while len(st.session_state.components) < count:
        next_index = len(st.session_state.components) + 1
        st.session_state.components.append(
            {
                "name": f"Component {next_index}",
                "method": "Model fit",
                "model": "Langmuir",
                "fill_value": None,
                "data": pd.DataFrame({"Pressure": [1.0, 10.0, 50.0], "Loading": [1.0, 4.0, 8.0]}),
            }
        )
    while len(st.session_state.components) > count:
        st.session_state.components.pop()
    st.session_state.fractions = normalize_fractions(st.session_state.fractions, count)

    st.divider()
    fraction_label = "Gas fractions" if mode == "Forward IAST" else "Adsorbed fractions"
    st.subheader(fraction_label)
    fractions = []
    for index, component in enumerate(st.session_state.components):
        fractions.append(
            st.number_input(
                component["name"],
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state.fractions[index]),
                step=0.01,
                key=f"fraction_{index}",
            )
        )
    if st.button("Normalize fractions", use_container_width=True):
        st.session_state.fractions = normalize_fractions(fractions, count)
        st.rerun()

tabs = st.tabs(["Pure Component Data", "Results"])

with tabs[0]:
    columns = st.columns(2)
    components = []
    for index, item in enumerate(st.session_state.components):
        with columns[index % 2]:
            components.append(render_component_editor(index, item))

with tabs[1]:
    fractions = normalize_fractions(fractions, len(components))
    st.session_state.fractions = fractions

    run = st.button("Run calculation", type="primary", use_container_width=True)
    if run:
        try:
            isotherms = [build_isotherm(component) for component in components]
            if mode == "Forward IAST":
                result = run_forward_iast(components, isotherms, total_pressure, fractions)
            else:
                result = run_reverse_iast(components, isotherms, total_pressure, fractions)

            st.subheader("Mixture prediction")
            st.dataframe(result, use_container_width=True, hide_index=True)
            st.metric("Total loading", f"{result['Loading'].sum():.6g}")

            st.subheader("Isotherm fits")
            st.pyplot(plot_isotherms(components, isotherms), use_container_width=True)

            st.subheader("Model parameters")
            st.dataframe(parameter_rows(components, isotherms), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(str(exc))
    else:
        st.info("Set up the component data and fractions, then run the calculation.")
