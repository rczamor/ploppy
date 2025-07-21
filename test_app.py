import streamlit as st

st.set_page_config(page_title="Test App", layout="wide")

st.title("Test App")
st.write("If you can see this, Streamlit is working!")
st.success("✅ Basic Streamlit functionality confirmed")

# Test session state
if 'counter' not in st.session_state:
    st.session_state.counter = 0

if st.button("Click me"):
    st.session_state.counter += 1
    st.write(f"Button clicked {st.session_state.counter} times")