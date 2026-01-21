
try:
    import streamlit_autorefresh
    print('autorefresh: installed')
except ImportError:
    print('autorefresh: missing')

try:
    import pyarrow
    print('pyarrow: installed')
except ImportError:
    print('pyarrow: missing')

try:
    import plotly
    print('plotly: installed')
except ImportError:
    print('plotly: missing')
