import plotly.graph_objects as go
from plotly.subplots import make_subplots

def plot_head_distribution(dataframe, title="Head Distribution: Histogram + Box Plot"):
    """
    Plot a histogram and a horizontal box plot of the 'head' values
    from the inserted dataframe
    """
    # Drop NaNs
    head_data = dataframe["head"].dropna()

    # Create subplot with 2 rows: box plot on top, histogram below
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.2, 0.8],
        shared_xaxes=True,
        vertical_spacing=0.02
    )

    # 1) Horizontal box plot (on top)
    fig.add_trace(
        go.Box(
            x=head_data,
            boxpoints="outliers",
            orientation="h",
            name="Box Plot",
            marker_color="black",
            line=dict(width=1),
            fillcolor="lightgray",
            opacity=0.8
        ),
        row=1, col=1
    )

    # 2) Histogram (on bottom)
    fig.add_trace(
        go.Histogram(
            x=head_data,
            nbinsx=50,
            name="Histogram",
            marker_color="skyblue",
            opacity=0.75
        ),
        row=2, col=1
    )

    # Layout and styling
    fig.update_layout(
        title=dict(
            text=title,
            y=0.95,
            x=0.5,
            xanchor="center",
            yanchor="top"
        ),
        template="plotly_white",
        showlegend=False,
        margin=dict(t=60, r=30, b=60, l=60),
        height=500
    )

    fig.update_xaxes(title_text="Head (m)", row=2, col=1)
    fig.update_yaxes(title_text="Count", row=2, col=1)

    return fig


def plot_flagged_head_timeseries(dataframe, title="Head Time Series with Flags"):
    """
    Plot the head time series and highlight:
    - Outliers based on boxplot IQR method
    - Significant drops (>0.05 m) and jumps (>0.3 m) from head_t1
    Also includes precipitation, evapotranspiration, and recharge on the primary y-axis.
    """
    # Clip to first and last valid head entry
    first_valid = dataframe["head"].first_valid_index()
    last_valid = dataframe["head"].last_valid_index()
    if first_valid is not None and last_valid is not None:
        dataframe = dataframe.loc[first_valid:last_valid]
    else:
        raise ValueError("No valid head data to plot.")

    # Drop NaNs for head and head_t1
    head_series = dataframe["head"].dropna()
    head_t1_series = dataframe["head_t1"].dropna()

    # --- Detect outliers using IQR method ---
    Q1 = head_series.quantile(0.25)
    Q3 = head_series.quantile(0.75)
    IQR = Q3 - Q1
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR
    outlier_mask = (head_series < lower_bound) | (head_series > upper_bound)

    # --- Detect significant jumps/drops ---
    jump_mask = head_t1_series > 0.3
    drop_mask = head_t1_series < -0.05

    # --- Create subplot with secondary y-axis ---
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 1) Add bars for precipitation, evapotranspiration, and recharge (primary y)
    if "Precipitation" in dataframe.columns:
        fig.add_bar(
            name="Precipitation",
            x=dataframe.index,
            y=dataframe["Precipitation"],
            opacity=0.6,
            marker_line_width=0,
        )

    if "Evapotranspiration" in dataframe.columns:
        fig.add_bar(
            name="Evapotranspiration",
            x=dataframe.index,
            y=dataframe["Evapotranspiration"],
            opacity=0.6,
            marker_line_width=0,
        )

    if "recharge" in dataframe.columns:
        fig.add_bar(
            name="Recharge",
            x=dataframe.index,
            y=dataframe["recharge"],
            opacity=0.6,
            marker_line_width=0,
            marker=dict(color="purple"),
        )

    # 2) Main head time series (secondary y)
    fig.add_trace(go.Scatter(
        x=dataframe.index,
        y=dataframe["head"],
        mode="lines",
        name="Head",
        line=dict(color="black", width=1.5)
    ), secondary_y=True)

    # 3) Outliers on head (secondary y)
    fig.add_trace(go.Scatter(
        x=head_series[outlier_mask].index,
        y=head_series[outlier_mask],
        mode="markers",
        name="Boxplot Outlier",
        marker=dict(color="red", size=8, symbol="circle-open"),
        hoverinfo="x+y"
    ), secondary_y=True)

    # 4) Jumps > 0.3m (secondary y)
    fig.add_trace(go.Scatter(
        x=head_t1_series[jump_mask].index,
        y=dataframe.loc[head_t1_series[jump_mask].index, "head"],
        mode="markers",
        name="Jump > 0.3m",
        marker=dict(color="blue", size=8, symbol="triangle-up")
    ), secondary_y=True)

    # 5) Drops > 0.05m (secondary y)
    fig.add_trace(go.Scatter(
        x=head_t1_series[drop_mask].index,
        y=dataframe.loc[head_t1_series[drop_mask].index, "head"],
        mode="markers",
        name="Drop > 0.05m",
        marker=dict(color="orange", size=8, symbol="triangle-down")
    ), secondary_y=True)

    # --- Layout ---
    fig.update_layout(
        title=title,
        template="plotly_white",
        hovermode="x unified",
        barmode="overlay",
        height=600,
        legend=dict(orientation="h", y=1.05, x=1, xanchor="right"),
        margin=dict(t=80, r=20, b=40, l=60),
    )

    # --- Y-axis labels ---
    fig.update_yaxes(
        title_text="Precip / Evapo / Recharge (mm)",
        secondary_y=False,
        rangemode="tozero"
    )

    fig.update_yaxes(
        title_text="Head (m)",
        secondary_y=True
    )

    return fig